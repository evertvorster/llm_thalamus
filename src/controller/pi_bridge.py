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
    tool_execution_end = Signal(str, str, str, bool, object) # toolCallId, toolName,
                                                               #   result_text, isError, details

    # ── lifecycle ───────────────────────────────────────────────────────
    busy_changed = Signal(bool)
    error = Signal(str)

    # ── history loading ─────────────────────────────────────────────────
    history_turn = Signal(str, str, str)   # role, content, timestamp
    history_thinking = Signal(str, str)     # thinking_text, timestamp

    # ── command acknowledgement ─────────────────────────────────────────
    response_received = Signal(str, object)   # command name, response object

    # ── compaction ──────────────────────────────────────────────────────
    compact_start = Signal(str)          # reason: "manual"|"threshold"|"overflow"
    compact_end = Signal(str, object)    # reason, result dict or None

    # ── extension UI ────────────────────────────────────────────────────
    extension_ui_dialog = Signal(str, str, str, object)  # request_id, method,
                                                          #   title, data_dict
    extension_ui_notify = Signal(str, str)                # message, notify_type
    extension_ui_status = Signal(str, str)                # status_key, status_text

    # ────────────────────────────────────────────────────────────────────

    def __init__(self, pi_config_dir: str = "", parent: QObject | None = None):
        super().__init__(parent)
        self._pi_config_dir: str = pi_config_dir
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._running: bool = False

    # ── public API ──────────────────────────────────────────────────────

    def start(self, resume: bool = True, session_path: str | None = None) -> None:
        """Spawn ``pi --mode rpc`` and start the reader thread.

        Args:
            resume:       If True, auto-resume the most recent session (``-c``).
            session_path: If given, resume a specific session (``--session``).
                          Overrides ``resume``.
        """
        env = dict(os.environ)
        if self._pi_config_dir:
            env["PI_CODING_AGENT_DIR"] = self._pi_config_dir
        env["PI_OFFLINE"] = "1"

        args = ["pi", "--mode", "rpc"]
        if session_path:
            args += ["--session", str(session_path)]
        elif resume:
            args += ["-c"]

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

    def send_extension_ui_response(
        self, request_id: str, response: dict
    ) -> None:
        """Send an ``extension_ui_response`` back to pi.

        Called from the main thread (Qt slot) after the user has responded
        to a permission / input dialog.
        """
        self._send(
            {"type": "extension_ui_response", "id": request_id, **response}
        )

    def load_history(self) -> None:
        """Request the full message history from pi.

        Responses arrive as ``history_turn`` signals when the
        ``get_messages`` response is received.
        """
        self._send({"type": "get_messages"})

    def restart(self, cwd: str, session_path: str | None = None) -> None:
        """Shutdown pi and restart it from *cwd* (a new working directory).

        After ``_on_new_session`` picks a directory different from the current
        CWD, the bridge must be restarted because pi's CWD is set at process
        launch and cannot change.

        When *session_path* is provided, pi resumes that specific session.
        When ``None`` (default), pi auto‑resumes the most recent session with
        the ``-c`` flag.
        """
        self.shutdown()

        env = dict(os.environ)
        if self._pi_config_dir:
            env["PI_CODING_AGENT_DIR"] = self._pi_config_dir
        env["PI_OFFLINE"] = "1"

        args = ["pi", "--mode", "rpc"]
        if session_path:
            args.extend(["--session", session_path])
        else:
            args.append("-c")
        self._process = subprocess.Popen(
            args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        # Reset any stale busy state from the previous process.
        self.busy_changed.emit(False)

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

        # ── message lifecycle ────────────────────────────
        if et == "message_start":
            # pi emits message_start for every message (assistant, tool results).
            # turn_start already fires assistant_stream_start; silence the warning.
            return
        if et == "turn_end":
            # turn_end brackets the end of a turn.  message_end already fired
            # assistant_stream_end.  Nothing to do here.
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
                result.get("details") if isinstance(result, dict) else None,
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
            # Handle get_messages — emit structured history so tool
            # calls and results render as tool stacks rather than
            # separate chat bubbles, and thinking blocks are preserved.
            if event.get("command") == "get_messages" and event.get("success"):
                data = event.get("data", {})
                messages = data.get("messages", []) if isinstance(data, dict) else []
                self._emit_structured_history(messages)
            return

        # ── extension UI requests ───────────────────────────
        if et == "extension_ui_request":
            self._route_extension_ui(event)
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
        elif at == "text_start":
            # Content block boundary — text_delta events follow with actual text.
            pass
        elif at == "text_end":
            # Content block boundary — text_delta already delivered the content.
            pass
        elif at in ("toolcall_start", "toolcall_delta", "toolcall_end"):
            # Tool call announcements within the message stream are
            # informational — the real tool lifecycle is driven by
            # tool_execution_start/update/end events.
            pass
        elif at == "error":
            self.error.emit(ame.get("reason", "stream error"))
        else:
            print(
                f"[pi_bridge] unrecognised message update type: {at}",
                file=sys.stderr,
            )


    # ── extension UI routing ───────────────────────────────────

    def _route_extension_ui(self, event: dict) -> None:
        """Route an ``extension_ui_request`` to the appropriate signal."""
        method = event.get("method", "")
        request_id = str(event.get("id", ""))

        if method in ("select", "confirm", "input", "editor"):
            # Dialog methods — pi blocks waiting for a response.
            title = str(event.get("title") or "")
            data: dict[str, object] = {}
            for key in ("message", "options", "placeholder", "prefill"):
                val = event.get(key)
                if val is not None:
                    data[key] = val
            self.extension_ui_dialog.emit(request_id, method, title, data)
        elif method == "notify":
            self.extension_ui_notify.emit(
                str(event.get("message", "")),
                str(event.get("notifyType", "info")),
            )
        elif method == "setStatus":
            key = str(event.get("statusKey", ""))
            text = event.get("statusText")
            if text is not None and key:
                self.extension_ui_status.emit(key, str(text))
            elif key:
                # statusText omitted or undefined → clear this status entry.
                self.extension_ui_status.emit(key, "")
        elif method in ("setWidget", "setTitle", "set_editor_text"):
            # Fire-and-forget — log visibly for now.
            self.extension_ui_notify.emit(
                f"extension ui: {method}", "info"
            )
        else:
            self.extension_ui_notify.emit(
                f"extension ui: unknown method {method}", "warning"
            )

    # ── history emission ──────────────────────────────────────

    def _emit_structured_history(self, messages: list[dict]) -> None:
        """Emit tool and text events from a list of pi AgentMessages.

        Unlike the old flat ``history_turn(role, flat_string)`` approach,
        this method:

        * Extracts ``toolCall`` blocks from assistant messages and emits
          ``tool_execution_start`` / ``tool_execution_end`` for each
          one (matched with the corresponding ``toolResult`` message).
        * Preserves ``thinking`` blocks as separate thinking bubbles via the
          ``history_thinking`` signal, so they render as collapsible cards.
        * Skips ``toolResult`` and ``bashExecution`` messages as
          separate bubbles — they are rendered in tool stacks or
          omitted respectively.
        """
        # ── pass 1: index tool results by toolCallId ──────────
        tool_results: dict[str, dict] = {}
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "toolResult":
                cid = str(msg.get("toolCallId", ""))
                if cid:
                    tool_results[cid] = msg

        # ── pass 2: emit structured history ────────────────────
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "unknown")
            ts = str(msg.get("timestamp", ""))
            content = msg.get("content", "")

            if role == "user":
                text = _str_content(content)
                self.history_turn.emit("user", text, ts)

            elif role == "assistant":
                if isinstance(content, list):
                    text_parts: list[str] = []
                    thinking_parts: list[str] = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        bt = block.get("type", "")
                        if bt == "text":
                            text_parts.append(str(block.get("text", "")))
                        elif bt == "thinking":
                            thinking_parts.append(
                                str(block.get("thinking", ""))
                            )
                        elif bt == "toolCall":
                            call_id = str(block.get("id", ""))
                            name = str(block.get("name", ""))
                            # args may be a dict or stringified JSON
                            args = block.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except (json.JSONDecodeError, TypeError):
                                    args = {}
                            if not isinstance(args, dict):
                                args = {}
                            self.tool_execution_start.emit(
                                call_id, name, args
                            )
                            result_msg = tool_results.get(call_id)
                            if result_msg is not None:
                                result_text = _str_content(
                                    result_msg.get("content", "")
                                )
                                self.tool_execution_end.emit(
                                    call_id, name, result_text,
                                    result_msg.get("isError", False),
                                    None,  # details — not available in history
                                )
                    text = "".join(text_parts)
                    thinking = "".join(thinking_parts)
                    if thinking:
                        self.history_thinking.emit(thinking, ts)
                    if text:
                        self.history_turn.emit("assistant", text, ts)
                    elif not thinking:
                        # Failed turn — show the error message.
                        error_msg = msg.get("errorMessage", "")
                        if error_msg:
                            self.history_turn.emit("assistant", str(error_msg), ts)
                else:
                    self.history_turn.emit(
                        "assistant", _str_content(content), ts
                    )

            elif role == "toolResult":
                # Rendered via tool_execution_end emitted above.
                pass

            elif role == "bashExecution":
                # Pre-prompt bash — not UI-relevant for history.
                pass


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


def _str_content(content: object) -> str:
    """Convert a pi message content field to a plain string.

    Handles plain strings, arrays of ``{type: text, text: ...}`` blocks,
    and fallback ``str()`` for unexpected shapes.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)
