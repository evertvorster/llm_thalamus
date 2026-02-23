from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QThread

from controller.chat_history import append_turn, read_tail
from controller.world_state import load_world_state, commit_world_state
from controller.runtime_services import build_runtime_services

from runtime.deps import build_runtime_deps
from runtime.langgraph_runner import run_turn_runtime
from runtime.state import new_runtime_state


def _now_iso_local() -> str:
    # Local timezone ISO8601 with seconds.
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ControllerWorker(QObject):
    busy_changed = Signal(bool)

    # Legacy one-shot assistant output (still used for error fallback).
    assistant_message = Signal(str)

    # Streaming assistant output (chat bubble streaming).
    assistant_stream_start = Signal()
    assistant_stream_delta = Signal(str)
    assistant_stream_end = Signal()

    error = Signal(str)

    # --- thinking channel (ephemeral, per-request) ---
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()

    # role, content, ts
    history_turn = Signal(str, str, str)

    # single log line intended for the combined logs window (thalamus log)
    log_line = Signal(str)

    # world state has been committed (used by UI to refresh the world summary widget)
    world_committed = Signal()

    # mid-turn world update (UI debugging)
    world_updated = Signal(object)

    # sanitized state snapshot updates (UI debugging)
    state_updated = Signal(object)

    def __init__(self, cfg):
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

        # --- world state (authoritative path) ---
        world_state_path = self._compute_world_state_path()
        self._world_state_path = str(world_state_path)
        self._world = load_world_state(path=world_state_path, now_iso=_now_iso_local())

        # --- runtime services (tools/resources) ---
        tz = str(getattr(self._cfg, "tz", "") or getattr(self._cfg, "timezone", "") or "")

        # MCP settings (resolved via ConfigSnapshot -> EffectiveValues -> schema)
        mcp_openmemory_url = str(getattr(self._cfg, "mcp_openmemory_url", "") or "")
        mcp_openmemory_api_key = str(getattr(self._cfg, "mcp_openmemory_api_key", "") or "")
        mcp_protocol_version = str(getattr(self._cfg, "mcp_protocol_version", "2025-06-18") or "2025-06-18")

        self._runtime_services = build_runtime_services(
            history_file=self._history_file,
            world_state_path=world_state_path,
            now_iso=_now_iso_local(),
            tz=tz,
            mcp_openmemory_url=(mcp_openmemory_url or None),
            mcp_openmemory_api_key=(mcp_openmemory_api_key or None),
            mcp_protocol_version=mcp_protocol_version,
        )

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

    @property
    def world_state_path(self) -> str:
        """Absolute path to the current world_state.json used by the controller."""
        return self._world_state_path

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
        self.log_line.emit("[cfg] reload_config ignored (runtime-only graph; worker retains cfg snapshot)")

    def emit_history(self) -> None:
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
            ts_user = _now_iso_local()
            if str(self._history_file):
                append_turn(
                    history_file=self._history_file,
                    role="human",
                    content=text,
                    max_turns=self._history_max,
                    ts=ts_user,
                )

            deps = build_runtime_deps(self._cfg)
            state = new_runtime_state(user_text=text)

            state["world"] = dict(self._world) if isinstance(self._world, dict) else {}

            self.log_line.emit("[runtime] run_turn_runtime start")

            assistant_buf: str = ""
            assistant_started = False
            assistant_ended = False

            final_world: Optional[dict] = None

            for ev in run_turn_runtime(state, deps, self._runtime_services):
                et = ev.get("type")
                payload = ev.get("payload") or {}

                if et == "node_start":
                    node_id = str(ev.get("node_id", "") or "")
                    self.log_line.emit(f"[runtime] node_start {node_id}")
                    _emit_thinking_started_once()
                    label = str(payload.get("label", "") or "")
                    header = label if label else node_id
                    self.thinking_delta.emit(f"\n── {header} ──\n")

                elif et == "node_end":
                    node_id = str(ev.get("node_id", "") or "")
                    status = str(payload.get("status", "") or "")
                    self.log_line.emit(f"[runtime] node_end {node_id} ({status})")

                elif et == "log_line":
                    level = str(payload.get("level", "") or "")
                    logger = str(payload.get("logger", "") or "")
                    msg = str(payload.get("message", "") or "")
                    self.log_line.emit(f"[{level}] {logger}: {msg}")

                elif et == "thinking_delta":
                    _emit_thinking_started_once()
                    chunk = str(payload.get("text", "") or "")
                    if chunk:
                        self.thinking_delta.emit(chunk)

                elif et == "assistant_start":
                    assistant_buf = ""
                    assistant_started = True
                    assistant_ended = False
                    self.assistant_stream_start.emit()

                elif et == "assistant_delta":
                    chunk = str(payload.get("text", "") or "")
                    if chunk:
                        assistant_buf += chunk
                        self.assistant_stream_delta.emit(chunk)

                elif et == "assistant_end":
                    assistant_ended = True
                    self.assistant_stream_end.emit()

                    ts_asst = _now_iso_local()
                    if str(self._history_file):
                        append_turn(
                            history_file=self._history_file,
                            role="you",
                            content=assistant_buf,
                            max_turns=self._history_max,
                            ts=ts_asst,
                        )

                elif et == "world_commit":
                    w = payload.get("world_after")
                    if isinstance(w, dict):
                        final_world = w

                elif et == "world_update":
                    w = payload.get("world")
                    if isinstance(w, dict):
                        self._world = w
                        self.world_updated.emit(w)

                elif et == "state_update":
                    s = payload.get("state")
                    if isinstance(s, dict):
                        self.state_updated.emit(s)

                elif et == "turn_end":
                    status = str(payload.get("status", "") or "")
                    if status == "error":
                        err = payload.get("error") or {}
                        msg = str(err.get("message", "Unknown runtime error") or "Unknown runtime error")
                        self.log_line.emit(f"[runtime] turn_end error: {msg}")

            if not assistant_started or not assistant_ended:
                self.log_line.emit("[runtime] ERROR: graph terminated without assistant_end (no streamed reply)")
                fallback = (
                    "Internal error: runtime graph terminated without producing a final answer.\n"
                    "Check the thinking log above for the last node reached."
                )
                self.assistant_message.emit(fallback)

                ts_asst = _now_iso_local()
                if str(self._history_file):
                    append_turn(
                        history_file=self._history_file,
                        role="you",
                        content=fallback,
                        max_turns=self._history_max,
                        ts=ts_asst,
                    )

            if isinstance(final_world, dict):
                self._world = final_world
                commit_world_state(path=Path(self._world_state_path), world=self._world)
                self.world_updated.emit(self._world)
                self.world_committed.emit()
            else:
                self.log_line.emit("[world] WARNING: runtime did not provide final world; not committing")
                self.world_committed.emit()

        except Exception as e:
            self.log_line.emit(f"[controller] error: {e}")
            self.error.emit(str(e))

        finally:
            if thinking_started_emitted:
                self.thinking_finished.emit()
            self.busy_changed.emit(False)