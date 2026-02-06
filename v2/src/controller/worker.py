from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot, QThread

from chat_history import append_turn, read_tail


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    assistant_message = Signal(str)
    error = Signal(str)

    # --- thinking channel (ephemeral, per-request) ---
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()

    # role, content, ts
    history_turn = Signal(str, str, str)

    # single log line intended ...
    log_line = Signal(str)

    def __init__(self, cfg, openmemory_client=None):
        super().__init__()
        self._cfg = cfg
        self._openmemory = openmemory_client

        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

        self._turn_seq = 0
        self._turn_lock = threading.Lock()

        self.log_line.emit("ControllerWorker started.")

    # ---------- public API (called by UI) ----------

    @Slot(str)
    def submit_message(self, text: str) -> None:
        if not text.strip():
            return

        self.log_line.emit(f"[ui] submit_message len={len(text)}")
        self.busy_changed.emit(True)

        threading.Thread(
            target=self._handle_message,
            args=(text,),
            daemon=True,
        ).start()

    @Slot()
    def reload_config(self) -> None:
        # MVP: UI rewrites config on disk; controller reload can be improved later
        try:
            from config import bootstrap_config
            self._cfg = bootstrap_config([])
            self.log_line.emit("[cfg] reloaded config from disk")
        except Exception as e:
            self.log_line.emit(f"[cfg] reload FAILED: {e}")
            self.error.emit(f"Config reload failed: {e}")

    def emit_history(self) -> None:
        """
        Emit the last N turns from history so the UI can render them as historical.
        """
        try:
            turns = read_tail(self._cfg.message_file, limit=self._cfg.history_message_limit)
            self.log_line.emit(f"[history] loaded {len(turns)} turns from {self._cfg.message_file}")
            for t in turns:
                self.history_turn.emit(t.role, t.content, t.ts)
        except Exception as e:
            self.log_line.emit(f"[history] load FAILED: {e}")
            self.error.emit(f"History load failed: {e}")

    def shutdown(self) -> None:
        """
        Stop the worker QThread cleanly so we don't get:
          'QThread: Destroyed while thread is still running'
        """
        try:
            if self._thread.isRunning():
                self.log_line.emit("[ui] shutdown: stopping controller thread")
                self._thread.quit()
                self._thread.wait(2000)
        except Exception as e:
            # Don't raise during shutdown
            try:
                self.log_line.emit(f"[ui] shutdown: exception: {e}")
            except Exception:
                pass

    # ---------- internal logic ----------

    def _next_turn(self) -> tuple[int, str]:
        with self._turn_lock:
            self._turn_seq += 1
            seq = self._turn_seq
        return seq, f"turn-{seq}"

    def _handle_message(self, text: str) -> None:
        thinking_started_emitted = False

        def _emit_thinking_started_once() -> None:
            nonlocal thinking_started_emitted
            if not thinking_started_emitted:
                thinking_started_emitted = True
                self.thinking_started.emit()

        try:
            append_turn(
                history_file=self._cfg.message_file,
                role="human",
                content=text,
                max_turns=self._cfg.message_history_max,
            )

            turns = read_tail(self._cfg.message_file, limit=self._cfg.history_message_limit)
            messages = [{"role": t.role, "content": t.content} for t in turns]

            turn_seq, turn_id = self._next_turn()

            from orchestrator.deps import build_deps
            from orchestrator.runner_seq import run_turn_seq
            from orchestrator.state import new_state_for_turn

            if self._openmemory is None:
                raise RuntimeError(
                    "OpenMemory is not initialized: ControllerWorker was created without openmemory_client"
                )

            deps = build_deps(self._cfg, self._openmemory)
            state = new_state_for_turn(
                turn_id=turn_id,
                user_input=text,
                messages=messages,
                turn_seq=turn_seq,
            )

            self.log_line.emit("[orchestrator] run_turn_seq start")

            final_answer: str | None = None

            for ev in run_turn_seq(state, deps):
                et = ev.get("type")

                if et == "node_start":
                    _emit_thinking_started_once()
                    node = str(ev.get("node", ""))
                    self.log_line.emit(f"[orchestrator] node_start {node}")
                    self.thinking_delta.emit(f"[{node}]")

                elif et == "node_end":
                    node = str(ev.get("node", ""))
                    self.log_line.emit(f"[orchestrator] node_end {node}")

                elif et == "log":
                    _emit_thinking_started_once()
                    text_chunk = str(ev.get("text", ""))
                    # forward to UI as live thinking delta
                    if text_chunk:
                        self.thinking_delta.emit(text_chunk)

                elif et == "final":
                    final_answer = str(ev.get("answer", "")).strip()

            if final_answer is None:
                raise RuntimeError("Orchestrator produced no final answer")

            self.log_line.emit(f"[orchestrator] final len={len(final_answer)}")

            append_turn(
                history_file=self._cfg.message_file,
                role="you",
                content=final_answer,
                max_turns=self._cfg.message_history_max,
            )

            self.assistant_message.emit(final_answer)

        except Exception as e:
            self.log_line.emit(f"[error] orchestrator failed: {e}")
            self.error.emit(f"Orchestrator failed: {e}")

        finally:
            if thinking_started_emitted:
                self.thinking_finished.emit()
            self.busy_changed.emit(False)
