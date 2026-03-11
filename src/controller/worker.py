from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QThread

from controller.chat_history import append_turn, read_tail
from controller.world_state import load_world_state, commit_world_state
from controller.runtime_services import build_runtime_services
from controller.mcp.client import MCPServerConfig

from runtime.deps import build_runtime_deps
from runtime.langgraph_runner import run_turn_runtime
from runtime.state import new_runtime_state


def _now_iso_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    activity_event = Signal(object)
    assistant_message = Signal(str)
    assistant_stream_start = Signal()
    assistant_stream_delta = Signal(str)
    assistant_stream_end = Signal()
    error = Signal(str)
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()
    prompt_started = Signal()
    prompt_delta = Signal(str)
    prompt_finished = Signal()
    history_turn = Signal(str, str, str)
    log_line = Signal(str)
    world_committed = Signal()
    world_updated = Signal(object)
    state_updated = Signal(object)

    def __init__(self, cfg):
        super().__init__()
        self._cfg = cfg

        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

        self._history_file = Path(getattr(self._cfg, "message_file", "") or "").expanduser()
        self._history_limit = int(getattr(self._cfg, "history_message_limit", 50) or 50)
        self._history_max = int(getattr(self._cfg, "message_history_max", self._history_limit) or self._history_limit)

        world_state_path = self._compute_world_state_path()
        self._world_state_path = str(world_state_path)
        self._world = load_world_state(path=world_state_path, now_iso=_now_iso_local())

        tz = str(getattr(self._cfg, "tz", "") or getattr(self._cfg, "timezone", "") or "")

        mcp_servers: dict[str, MCPServerConfig] = {}
        mcp_openmemory_url = str(getattr(self._cfg, "mcp_openmemory_url", "") or "")
        mcp_openmemory_api_key = str(getattr(self._cfg, "mcp_openmemory_api_key", "") or "")
        mcp_protocol_version = str(getattr(self._cfg, "mcp_protocol_version", "2025-06-18") or "2025-06-18")
        if mcp_openmemory_url and mcp_openmemory_api_key:
            mcp_servers["openmemory"] = MCPServerConfig(
                server_id="openmemory",
                url=mcp_openmemory_url,
                headers={"X-API-Key": mcp_openmemory_api_key},
                protocol_version=mcp_protocol_version,
                client_name="llm_thalamus",
                client_version="0.0.1",
            )

        self._runtime_services = build_runtime_services(
            history_file=self._history_file,
            world_state_path=world_state_path,
            now_iso=_now_iso_local(),
            tz=tz,
            mcp_servers=mcp_servers or None,
        )

        self.log_line.emit("ControllerWorker started (runtime graph + worker-owned history/world).")

    def _compute_world_state_path(self) -> Path:
        sr = getattr(self._cfg, "state_root", None)
        if sr:
            return Path(sr) / "world_state.json"

        lf = getattr(self._cfg, "log_file", None)
        if lf:
            return Path(lf).parent.parent / "world_state.json"

        if str(self._history_file):
            return self._history_file.parent / "world_state.json"

        return Path.cwd() / "world_state.json"

    @property
    def world_state_path(self) -> str:
        return self._world_state_path

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

    def _handle_message(self, text: str) -> None:
        thinking_started_emitted = False
        prompt_started_emitted = False

        def _emit_thinking_started_once() -> None:
            nonlocal thinking_started_emitted
            if not thinking_started_emitted:
                thinking_started_emitted = True
                self.thinking_started.emit()

        def _emit_prompt_started_once() -> None:
            nonlocal prompt_started_emitted
            if not prompt_started_emitted:
                prompt_started_emitted = True
                self.prompt_started.emit()

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
                if et in {"node_start", "node_end", "tool_call", "tool_result"}:
                    self.activity_event.emit(ev)
                    continue
                if et == "turn_start":
                    _emit_thinking_started_once()
                    continue
                if et == "thinking_delta":
                    _emit_thinking_started_once()
                    self.thinking_delta.emit(str(payload.get("text") or ""))
                    continue
                if et == "assistant_start":
                    assistant_started = True
                    self.assistant_stream_start.emit()
                    continue
                if et == "assistant_delta":
                    delta = str(payload.get("text") or "")
                    assistant_buf += delta
                    self.assistant_stream_delta.emit(delta)
                    continue
                if et == "assistant_end":
                    assistant_ended = True
                    self.assistant_stream_end.emit()
                    continue
                if et == "log_line":
                    self.log_line.emit(str(payload.get("message") or ""))
                    continue
                if et == "llm_request":
                    _emit_prompt_started_once()
                    self.prompt_delta.emit(json.dumps(payload.get("request") or {}, ensure_ascii=False, indent=2))
                    continue
                if et == "world_update":
                    self.world_updated.emit(payload.get("world"))
                    continue
                if et == "state_update":
                    self.state_updated.emit(payload.get("state"))
                    continue
                if et == "world_commit":
                    fw = payload.get("world_after")
                    if isinstance(fw, dict):
                        final_world = fw
                    continue
                if et == "turn_end":
                    continue

            if assistant_started and not assistant_ended:
                self.assistant_stream_end.emit()

            ts_you = _now_iso_local()
            if assistant_buf.strip() and str(self._history_file):
                append_turn(
                    history_file=self._history_file,
                    role="you",
                    content=assistant_buf,
                    max_turns=self._history_max,
                    ts=ts_you,
                )

            if final_world is not None:
                commit_world_state(path=Path(self._world_state_path), world=final_world)
                self._world = dict(final_world)
                self.world_committed.emit()

            if assistant_buf.strip() and not assistant_started:
                self.assistant_message.emit(assistant_buf)

        except Exception as e:
            self.log_line.emit(f"[runtime] ERROR: {e}")
            self.error.emit(str(e))
        finally:
            self.thinking_finished.emit()
            self.prompt_finished.emit()
            self.busy_changed.emit(False)
