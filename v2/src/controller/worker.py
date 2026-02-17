from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot, QThread

from runtime.deps import build_runtime_deps
from runtime.langgraph_runner import run_turn_runtime
from runtime.state import new_runtime_state


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    assistant_message = Signal(str)
    error = Signal(str)

    # --- thinking channel (ephemeral, per-request) ---
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()

    # legacy UI hooks (kept for compatibility; not used in stripped mode)
    history_turn = Signal(str, str, str)
    log_line = Signal(str)
    world_committed = Signal()

    def __init__(self, cfg, openmemory_client=None):
        super().__init__()
        self._cfg = cfg

        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

        self.log_line.emit("ControllerWorker started (runtime-only).")

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
        # Keep this as a no-op for now (runtime-only strip). Your UI can still call it safely.
        self.log_line.emit("[cfg] reload_config ignored in runtime-only mode")

    def emit_history(self) -> None:
        # Stripped: no chat history persistence at this stage.
        self.log_line.emit("[history] emit_history ignored in runtime-only mode")

    def shutdown(self) -> None:
        try:
            if self._thread.isRunning():
                self.log_line.emit("[ui] shutdown: stopping controller thread")
                self._thread.quit()
                self._thread.wait(2000)
        except Exception as e:
            try:
                self.log_line.emit(f"[ui] shutdown: exception: {e}")
            except Exception:
                pass

    def _handle_message(self, text: str) -> None:
        thinking_started_emitted = False

        def _emit_thinking_started_once() -> None:
            nonlocal thinking_started_emitted
            if not thinking_started_emitted:
                thinking_started_emitted = True
                self.thinking_started.emit()

        try:
            deps = build_runtime_deps(self._cfg)
            state = new_runtime_state(user_text=text)

            final_answer: str | None = None

            for ev in run_turn_runtime(state, deps):
                et = ev.get("type")

                if et == "node_start":
                    _emit_thinking_started_once()
                    node = str(ev.get("node", ""))
                    self.thinking_delta.emit(f"[{node}]\n")

                elif et == "log":
                    _emit_thinking_started_once()
                    chunk = str(ev.get("text", ""))
                    if chunk:
                        self.thinking_delta.emit(chunk)

                elif et == "node_end":
                    # Optional; keeping for completeness / future UI highlighting
                    pass

                elif et == "final":
                    final_answer = str(ev.get("answer", "") or "")

            if final_answer is None:
                final_answer = (
                    "Internal error: runtime graph terminated without producing a final answer.\n"
                    "Check the thinking log for the last node reached."
                )

            self.assistant_message.emit(final_answer)

        except Exception as e:
            self.log_line.emit(f"[controller] error: {e}")
            self.error.emit(str(e))

        finally:
            if thinking_started_emitted:
                self.thinking_finished.emit()
            self.busy_changed.emit(False)
