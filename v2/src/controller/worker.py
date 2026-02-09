from __future__ import annotations

import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QThread

from chat_history import append_turn, read_tail
from orchestrator.world_state import WorldStateV1, load_world_state

_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


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

        # --- world state (authoritative, strict) ---
        self._world_state_path = self._compute_world_state_path()
        self._world: WorldStateV1 = self._load_world_at_startup()

        self.log_line.emit("ControllerWorker started.")

    # ---------- world state helpers ----------

    def _compute_world_state_path(self) -> Path:
        """
        Use cfg.state_root if present; otherwise fall back to the existing convention:
        <log_file parent>/../world_state.json
        """
        # Prefer explicit cfg.state_root if it exists on the snapshot.
        sr = getattr(self._cfg, "state_root", None)
        if sr:
            return Path(sr) / "world_state.json"

        # Fallback: consistent with your existing layout:
        # <state_root>/log/thalamus.log => state_root = log_file.parent.parent
        return Path(self._cfg.log_file).parent.parent / "world_state.json"

    def _load_world_at_startup(self) -> WorldStateV1:
        try:
            now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")
            w = load_world_state(path=self._world_state_path, now_iso=now_iso)
            self.log_line.emit(f"[world] loaded from {self._world_state_path}")
            return w
        except Exception as e:
            # If this fails, we should fail loudly: world_state is foundational.
            self.log_line.emit(f"[world] load FAILED: {e}")
            raise

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

            # Recompute world path in case roots changed, then reload once.
            self._world_state_path = self._compute_world_state_path()
            self._world = self._load_world_at_startup()

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
        reflection_started = False

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

            _ = read_tail(self._cfg.message_file, limit=self._cfg.history_message_limit)

            turn_seq, turn_id = self._next_turn()

            from orchestrator.deps import build_deps
            from orchestrator.langgraph_runner import run_turn_langgraph
            from orchestrator.state import new_state_for_turn
            from orchestrator.nodes.reflect_store_node import run_reflect_store_node

            if self._openmemory is None:
                raise RuntimeError(
                    "OpenMemory is not initialized: ControllerWorker was created without openmemory_client"
                )

            deps = build_deps(self._cfg, self._openmemory)

            state = new_state_for_turn(
                turn_id=turn_id,
                user_input=text,
                turn_seq=turn_seq,
            )

            # Make the authoritative world state available to the turn immediately.
            # (world_fetch may still run to create a different "view", but reflect/store
            # must always use the strict world state owned by ControllerWorker.)
            state["world"] = dict(self._world)

            self.log_line.emit("[orchestrator] run_turn_langgraph start")

            final_answer: str | None = None

            for ev in run_turn_langgraph(state, deps):
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

            def _run_reflection() -> None:
                try:
                    self.thinking_delta.emit("\n[reflect_store] start\n")

                    def _on_reflection_delta(chunk: str) -> None:
                        if chunk:
                            self.thinking_delta.emit(chunk)

                    def _on_memory_saved(mem_text: str) -> None:
                        self.thinking_delta.emit("\n[memory_saved]\n")
                        self.thinking_delta.emit(mem_text)
                        self.thinking_delta.emit("\n")

                    world_after = run_reflect_store_node(
                        state,
                        deps,
                        world_before=self._world,
                        world_state_path=self._world_state_path,
                        on_delta=_on_reflection_delta,
                        on_memory_saved=_on_memory_saved,
                    )

                    # Update in-memory world if a commit happened.
                    if world_after is not None:
                        self._world = world_after
                        # Keep state in sync for any downstream instrumentation.
                        state["world"] = dict(self._world)

                    self.thinking_delta.emit("\n[reflect_store] done\n")
                    self.log_line.emit("[memory] reflection+store completed")

                except Exception as e:
                    self.log_line.emit(f"[memory] reflection FAILED: {e}")
                    self.thinking_delta.emit(f"\n[reflect_store] FAILED: {e}\n")
                finally:
                    if thinking_started_emitted:
                        self.thinking_finished.emit()
                    self.busy_changed.emit(False)

            reflection_started = True
            threading.Thread(
                target=_run_reflection,
                daemon=True,
            ).start()

        except Exception as e:
            self.log_line.emit(f"[error] orchestrator failed: {e}")
            self.error.emit(f"Orchestrator failed: {e}")

        finally:
            if not reflection_started:
                if thinking_started_emitted:
                    self.thinking_finished.emit()
                self.busy_changed.emit(False)
