"""PiRPCBridge — spawns pi --mode rpc and emits Qt signals from its event stream."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class PiRPCBridge(QObject):
    """Spawns `pi --mode rpc` as a subprocess and emits Qt signals from the RPC event stream.

    The reader thread reads JSONL from pi's stdout and routes each event to the
    appropriate signal.  Qt signals are thread-safe, so emitting from the reader
    thread is safe.

    Constructor args:
        pi_config_dir:  If non-empty, set as ``PI_CODING_AGENT_DIR`` in the
                        subprocess environment.  Default ``""`` (no override).
    """

    # ── message streaming ──────────────────────────────────────────────
    assistant_stream_start = Signal()
    assistant_stream_delta = Signal(str)
    assistant_stream_end = Signal()

    # ── thinking / reasoning blocks ─────────────────────────────────────
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()

    # ── tool execution ──────────────────────────────────────────────────
    tool_execution_start = Signal(str, str, dict)   # toolCallId, toolName, args
    tool_execution_update = Signal(str, str)         # toolCallId, partial_text
    tool_execution_end = Signal(str, str, str, bool) # toolCallId, toolName,
                                                     #   result_text, isError

    # ── lifecycle ───────────────────────────────────────────────────────
    busy_changed = Signal(bool)
    error = Signal(str)

    # ── history loading ─────────────────────────────────────────────────
    history_turn = Signal(str, str, str)   # role, content, timestamp

    # ── command acknowledgement ─────────────────────────────────────────
    response_received = Signal(str, object)   # command name, response object

    # ── compaction ──────────────────────────────────────────────────────
    compact_start = Signal(str)          # reason: "manual"|"threshold"|"overflow"
    compact_end = Signal(str, object)    # reason, result dict or None

    # ────────────────────────────────────────────────────────────────────

    def __init__(self, pi_config_dir: str = "", parent: QObject | None = None):
        super().__init__(parent)
        self._pi_config_dir: str = pi_config_dir
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._running: bool = False

    # ── public API ──────────────────────────────────────────────────────

    def start(self, session_path: str | None = None) -> None:
        """Spawn ``pi --mode rpc`` and start the reader thread.

        Args:
            session_path:  If given, passed as ``--session <path>`` to resume
                           an existing pi session.
        """
        env = dict(os.environ)
        if self._pi_config_dir:
            env["PI_CODING_AGENT_DIR"] = self._pi_config_dir
        env["PI_OFFLINE"] = "1"

        args = ["pi", "--mode", "rpc"]
        if session_path:
            args += ["--session", str(session_path)]

        self._process = subprocess.Popen(
            args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def submit_message(
        self, text: str, images: list[dict] | None = None
    ) -> None:
        """Send a user prompt to pi."""
        cmd: dict = {"type": "prompt", "message": text}
        if images:
            cmd["images"] = images
        self._send(cmd)

    def send_command(self, cmd: dict) -> None:
        """Send an arbitrary RPC command (e.g. set_model, new_session)."""
        self._send(cmd)

    def load_history(self) -> None:
        """Request the full message history from pi.

        Responses arrive as ``history_turn`` signals when the
        ``get_messages`` response is received.
        """
        self._send({"type": "get_messages"})

    def shutdown(self) -> None:
        """Stop the reader and terminate the subprocess."""
        self._running = False
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
            except OSError:
                pass

    # ── internal helpers ────────────────────────────────────────────────

    def _send(self, cmd: dict) -> None:
        proc = self._process
        if proc is None or proc.stdin is None:
            print("[pi_bridge] send: no process", file=sys.stderr)
            return
        line = json.dumps(cmd, ensure_ascii=False, separators=(",", ":")) + "\n"
        proc.stdin.write(line)
        proc.stdin.flush()

    def _read_loop(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            self._running = False
            self.error.emit("pi process has no stdout")
            return

        try:
            for line in proc.stdout:
                if not self._running:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[pi_bridge] bad JSON: {line!r}", file=sys.stderr)
                    continue
                self._route_event(event)
        except (OSError, ValueError) as exc:
            if self._running:
                self.error.emit(f"pi stdout read error: {exc}")
        finally:
            self._running = False
            # If the process died unexpectedly, emit an error.
            if proc is not None and proc.poll() is not None:
                rc = proc.returncode
                if rc != 0 and self._running is False:
                    # Only emit if we were still running (not a clean shutdown).
                    pass  # shutdown sets _running=False before terminate

    def _route_event(self, event: dict) -> None:
        et = event.get("type", "")

        # ── bracketing ─────────────────────────────────────────
        if et == "agent_start":
            self.busy_changed.emit(True)
            return
        if et == "agent_end":
            self.busy_changed.emit(False)
            return
        if et == "turn_start":
            self.assistant_stream_start.emit()
            return

        # ── message updates (streaming text + thinking) ───────
        if et == "message_update":
            self._route_message_update(event)
            return
        if et == "message_end":
            self.assistant_stream_end.emit()
            return

        # ── tool execution ────────────────────────────────────
        if et == "tool_execution_start":
            self.tool_execution_start.emit(
                event.get("toolCallId", ""),
                event.get("toolName", ""),
                event.get("args", {}),
            )
            return
        if et == "tool_execution_update":
            self.tool_execution_update.emit(
                event.get("toolCallId", ""),
                _extract_text_from_content(event.get("partialResult", {})),
            )
            return
        if et == "tool_execution_end":
            result = event.get("result", {})
            self.tool_execution_end.emit(
                event.get("toolCallId", ""),
                event.get("toolName", ""),
                _extract_text_from_content(result),
                event.get("isError", False),
            )
            return

        # ── errors ────────────────────────────────────────────
        if et == "auto_retry_end":
            if not event.get("success", True):
                self.error.emit(event.get("finalError", "Unknown error"))
            return

        # ── compaction ────────────────────────────────────────
        if et == "compaction_start":
            self.compact_start.emit(event.get("reason", "unknown"))
            return
        if et == "compaction_end":
            self.compact_end.emit(
                event.get("reason", "unknown"),
                event.get("result", None),
            )
            return

        # ── command acknowledgements ──────────────────────────
        if et == "response":
            self.response_received.emit(
                event.get("command", ""),
                event,
            )
            # Handle get_messages specially — emit history_turn
            # for each message so the UI can render history.
            if event.get("command") == "get_messages" and event.get("success"):
                data = event.get("data", {})
                messages = data.get("messages", []) if isinstance(data, dict) else []
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "unknown")
                    content = _msg_content_str(msg)
                    ts = str(msg.get("timestamp", ""))
                    self.history_turn.emit(role, content, ts)
            return

        # ── unrecognised ──────────────────────────────────────
        print(
            f"[pi_bridge] unrecognised event type: {et}",
            file=sys.stderr,
        )

    def _route_message_update(self, event: dict) -> None:
        ame = event.get("assistantMessageEvent")
        if not isinstance(ame, dict):
            return
        at = ame.get("type", "")

        if at == "text_delta":
            self.assistant_stream_delta.emit(ame.get("delta", ""))
        elif at == "thinking_start":
            self.thinking_started.emit()
        elif at == "thinking_delta":
            self.thinking_delta.emit(ame.get("delta", ""))
        elif at == "thinking_end":
            self.thinking_finished.emit()
        elif at in ("toolcall_start", "toolcall_delta", "toolcall_end"):
            # Tool call announcements within the message stream are
            # informational — the real tool lifecycle is driven by
            # tool_execution_start/update/end events.
            pass
        else:
            print(
                f"[pi_bridge] unrecognised message update type: {at}",
                file=sys.stderr,
            )


# ── helpers ──────────────────────────────────────────────────────────

def _extract_text_from_content(result: dict) -> str:
    """Extract concatenated text from an OpenAI-style content array."""
    content = result.get("content", [])
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _msg_content_str(msg: dict) -> str:
    """Turn a message's content field into a flat string.

    pi stores content as either a plain string or an array of content blocks.
    """
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _extract_text_from_content({"content": content})
    return str(content)
