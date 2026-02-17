from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QThread

from controller.chat_history import append_turn, read_tail
from controller.world_state import load_world_state

from runtime.deps import build_runtime_deps
from runtime.langgraph_runner import run_turn_runtime
from runtime.state import new_runtime_state


def _now_iso_local() -> str:
    # Local timezone ISO8601 with seconds.
    return datetime.now().astimezone().isoformat(timespec="seconds")


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

    # single log line intended for the combined logs window
    log_line = Signal(str)

    # world state has been committed (used by UI to refresh the world summary widget)
    world_committed = Signal()

    def __init__(self, cfg, openmemory_client=None):
        super().__init__()
        self._cfg = cfg

        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

        # --- chat history / world state (UI-facing) ---
        self._history_file = Path(getattr(self._cfg, "message_file", "") or "").expanduser()
        self._history_limit = int(getattr(self._cfg, "history_message_limit", 50) or 50)

        # Hard cap for on-disk trimming (JSONL rewrite). Prefer cfg.message_history_max if present.
        self._history_max = int(getattr(self._cfg, "message_history_max", self._history_limit) or self._history_limit)

        self._world_state_path = str(self._compute_world_state_path())
        self._world = load_world_state(path=Path(self._world_state_path), now_iso=_now_iso_local())

        self.log_line.emit("ControllerWorker started (runtime graph + worker-owned history/world).")

    # ---------- path helpers ----------

    def _compute_world_state_path(self) -> Path:
        """
        UI expects self._world_state_path to point at a world_state.json file.
        Prefer cfg.state_root if present, else fall back to the log_file convention,
        else place it next to the message file.
        """
        sr = getattr(self._cfg, "state_root", None)
        if sr:
            return Path(sr) / "world_state.json"

        lf = getattr(self._cfg, "log_file", None)
        if lf:
            # historical convention: <state_root>/log/... => state_root = log_file.parent.parent
            return Path(lf).parent.parent / "world_state.json"

        # last resort: keep it near chat history
        if str(self._history_file):
            return self._history_file.parent / "world_state.json"

        # last resort of last resort
        return Path.cwd() / "world_state.json"

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
        # Keep as no-op for now. You can wire runtime deps rebuild here later if needed.
        self.log_line.emit("[cfg] reload_config ignored (runtime-only graph; worker retains cfg snapshot)")

    def emit_history(self) -> None:
        """
        UI calls this on startup to populate the history panel.
        """
        try:
            if not str(self._history_file):
                return
            turns = read_tail(history_file=self._history_file, limit=self._history_limit)
            self.log_line.emit(f"[history] loaded {len(turns)} turns from {self._history_file}")
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
            try:
                self.log_line.emit(f"[ui] shutdown: exception: {e}")
            except Exception:
                pass

    # ---------- internal logic ----------

    def _handle_message(self, text: str) -> None:
        thinking_started_emitted = False

        def _emit_thinking_started_once() -> None:
            nonlocal thinking_started_emitted
            if not thinking_started_emitted:
                thinking_started_emitted = True
                self.thinking_started.emit()

        try:
            # ---- persist human turn (worker-owned, not runtime) ----
            ts_user = _now_iso_local()
            if str(self._history_file):
                append_turn(
                    history_file=self._history_file,
                    role="human",
                    content=text,
                    max_turns=self._history_max,
                    ts=ts_user,
                )

            # ---- build runtime deps + state ----
            deps = build_runtime_deps(self._cfg)
            state = new_runtime_state(user_text=text)

            # provide world snapshot for prompting (read-only for now)
            state["world"] = dict(self._world) if isinstance(self._world, dict) else {}

            self.log_line.emit("[runtime] run_turn_runtime start")

            final_answer: Optional[str] = None

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

                elif et == "final":
                    final_answer = str(ev.get("answer", "") or "")

            if final_answer is None:
                self.log_line.emit("[runtime] ERROR: graph terminated without final answer")
                final_answer = (
                    "Internal error: runtime graph terminated without producing a final answer.\n"
                    "Check the thinking log above for the last node reached."
                )

            # ---- emit answer to UI ----
            self.assistant_message.emit(final_answer)

            # ---- persist assistant turn ----
            ts_asst = _now_iso_local()
            if str(self._history_file):
                append_turn(
                    history_file=self._history_file,
                    role="you",
                    content=final_answer,
                    max_turns=self._history_max,
                    ts=ts_asst,
                )

            # ---- world state (display only, for now) ----
            # We are intentionally NOT mutating/committing world here yet.
            # Next step: make world updates a runtime node and only commit deltas output by the graph.
            #
            # Still, the UI world panel reads world_state.json from self._world_state_path.
            # We loaded it at startup, so it exists. Emit world_committed once to force refresh if needed.
            self.world_committed.emit()

        except Exception as e:
            self.log_line.emit(f"[controller] error: {e}")
            self.error.emit(str(e))

        finally:
            if thinking_started_emitted:
                self.thinking_finished.emit()
            self.busy_changed.emit(False)
