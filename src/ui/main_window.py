"""MainWindow — the central Qt window connecting PiRPCBridge signals to the UI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controller.pi_bridge import PiRPCBridge
from ui.chat_renderer import ChatRenderer
from ui.widgets import BrainWidget, ChatInput


class MainWindow(QWidget):
    """A minimal Qt window connecting PiRPCBridge signals to ChatRenderer."""

    def __init__(self, bridge: PiRPCBridge, graphics_dir: Path):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._bridge = bridge
        self._streaming: bool = False
        self._busy: bool = False
        self._provider: str = ""
        self._thinking_level: str = ""

        # --- left: chat renderer + input area ---
        self.chat = ChatRenderer()

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send)
        self.chat_input.textChanged.connect(self._on_input_text_changed)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.quit_button)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.chat, 1)
        left_layout.addLayout(input_row)

        # --- right: brain ---
        self.brain = BrainWidget(graphics_dir)
        self.brain.set_state("thalamus")
        self.brain.setMinimumSize(220, 220)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.brain, 0, Qt.AlignHCenter)
        right_layout.addStretch(1)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # --- status bar ---
        self._status_entries: dict[str, str] = {}

        self._status_frame = QFrame()
        self._status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._status_frame.setStyleSheet(
            "QFrame { border-top: 1px solid #ccc; padding: 2px 6px; background: #f5f5f7; }"
        )
        status_vlayout = QVBoxLayout(self._status_frame)
        status_vlayout.setContentsMargins(0, 0, 0, 0)
        status_vlayout.setSpacing(0)

        # ── row 1: path | tokens | context | model ─────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(6, 2, 6, 2)
        row1.setSpacing(16)

        self._path_label = QLabel(" ")
        self._path_label.setStyleSheet("font-size: 9pt; color: #444;")
        self._path_label.setToolTip("Working directory and git branch")
        row1.addWidget(self._path_label)
        row1.addStretch(1)

        self._tokens_label = QLabel(" ")
        self._tokens_label.setStyleSheet("font-size: 9pt; color: #666;")
        self._tokens_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._tokens_label.setToolTip("Input ↑ / Output ↓ tokens (k=thousands, M=millions) — R = cache reads")
        row1.addWidget(self._tokens_label)

        self._context_label = QLabel(" ")
        self._context_label.setStyleSheet("font-size: 9pt; color: #666;")
        self._context_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._context_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._context_label.setToolTip("Context window usage — current tokens / total window size")
        row1.addWidget(self._context_label)

        self._model_label = QLabel("-")
        self._model_label.setStyleSheet("font-size: 9pt; color: #444; font-weight: 600;")
        self._model_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._model_label.setToolTip("Provider and model — thinking level")
        row1.addWidget(self._model_label)

        status_vlayout.addLayout(row1)

        # ── row 2: extension status (hidden until populated) ─
        self._status_extras_label = QLabel("")
        self._status_extras_label.setStyleSheet(
            "font-size: 8pt; color: #888; padding: 1px 6px 2px 6px;"
        )
        self._status_extras_label.setToolTip("Extension status indicators (MemPalace, Memory capture)")
        self._status_extras_label.setVisible(False)
        status_vlayout.addWidget(self._status_extras_label)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(splitter, 1)
        root.addWidget(self._status_frame)

        # --- wire signals ---
        bridge.assistant_stream_start.connect(self._on_stream_start)
        bridge.assistant_stream_delta.connect(self._on_stream_delta)
        bridge.assistant_stream_end.connect(self._on_stream_end)
        bridge.thinking_started.connect(self._on_thinking_started)
        bridge.thinking_delta.connect(self._on_thinking_delta)
        bridge.thinking_finished.connect(self._on_thinking_finished)
        bridge.tool_execution_start.connect(self._on_tool_start)
        bridge.tool_execution_end.connect(self._on_tool_end)
        bridge.busy_changed.connect(self._on_busy)
        bridge.error.connect(self._on_error)
        bridge.history_turn.connect(self._on_history_turn)
        bridge.history_thinking.connect(self._on_history_thinking)
        bridge.extension_ui_dialog.connect(self._on_extension_ui_dialog)
        bridge.extension_ui_notify.connect(self._on_extension_ui_notify)
        bridge.extension_ui_status.connect(self._on_extension_ui_status)

        bridge.response_received.connect(self._on_response_received)

        # brain click opens the RPC event log (placeholder for now)
        self.brain.clicked.connect(lambda: print("[brain] clicked"))

        # Request initial status after startup.
        QTimer.singleShot(1200, self._refresh_status_bar)

        # Escape aborts the current agent operation.
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._escape_shortcut.activated.connect(self._on_escape)

    # ── slot: send / abort / steer ────────────────────────────────

    def _on_send(self) -> None:
        """Handle the Send/Stop button and ChatInput Enter key.

        When idle: Send button → ``prompt`` via ``submit_message``.
        When busy + typed text → ``steer`` via ``send_command``.
        When busy + no text (Stop button click) → ``abort``.
        """
        text = self.chat_input.toPlainText().strip()

        if self._busy:
            if not text:
                # Stop button clicked — abort the current operation.
                self._bridge.send_command({"type": "abort"})
                return
            # Steering message while agent is running — use a lightweight
            # insertion so the active assistant stream is not killed.
            self.chat.add_steer_message(text)
            self.chat_input.clear()
            self._bridge.send_command({"type": "steer", "message": text})
            return

        # Idle — normal prompt.
        if not text:
            return
        self.chat.add_turn("human", text)
        self.chat_input.clear()
        self._bridge.submit_message(text)

    # ── slots: streaming ─────────────────────────────────────────

    def _on_stream_start(self) -> None:
        """A turn has started. Don't create the assistant bubble yet — it would
        appear empty during the thinking phase. The first ``text_delta`` in
        ``_on_stream_delta`` creates the bubble lazily."""
        pass

    def _on_stream_delta(self, text: str) -> None:
        if not self._streaming:
            self._streaming = True
            self.chat.begin_assistant_stream()
        self.chat.append_assistant_delta(text)

    def _on_stream_end(self) -> None:
        self._streaming = False
        self.chat.end_assistant_stream()

    # ── slots: thinking ──────────────────────────────────────────

    def _on_thinking_started(self) -> None:
        self.brain.set_saturation(0.7)
        self.chat.add_thinking()  # create empty, expanded bubble

    def _on_thinking_delta(self, text: str) -> None:
        self.chat.append_thinking_delta(text)

    def _on_thinking_finished(self) -> None:
        self.brain.set_saturation(1.0)
        self.chat.end_thinking()  # finalize, collapse

    # ── slots: tools ─────────────────────────────────────────────

    def _on_tool_start(self, call_id: str, name: str, args: dict) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_call",
            "tool_call_id": call_id,
            "tool_name": name,
            "args": args,
        })

    def _on_tool_end(self, call_id: str, name: str, result_text: str, is_error: bool) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_result",
            "tool_call_id": call_id,
            "tool_name": name,
            "result": result_text,
            "ok": not is_error,
        })

    # ── slots: lifecycle ─────────────────────────────────────────

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setEnabled(True)
        self.brain.set_state("llm" if busy else "thalamus")
        if not busy:
            # Agent finished — refresh token / context stats.
            self._refresh_status_bar()

    def _on_input_text_changed(self) -> None:
        """Update the button label to reflect whether typing steers or aborts."""
        if self._busy:
            has_text = bool(self.chat_input.toPlainText().strip())
            self.send_button.setText("Steer" if has_text else "Stop")

    def _on_escape(self) -> None:
        """Escape key: abort the current agent operation if busy."""
        if self._busy:
            self._bridge.send_command({"type": "abort"})

    def _on_error(self, text: str) -> None:
        self.chat.add_turn("system", text)
        self.brain.set_state("inactive")

    def _on_history_turn(self, role: str, content: str, _ts: str) -> None:
        # Map pi roles to chat renderer roles.
        # pi roles: "user", "assistant", "toolResult", "bashExecution"
        display_role = "human" if role == "user" else "you"
        self.chat.add_turn(display_role, content)

    def _on_history_thinking(self, text: str, _ts: str) -> None:
        # History thinking bubbles start collapsed.
        self.chat.add_thinking(text)

    # ── slots: extension UI ───────────────────────────────────────

    def _on_extension_ui_dialog(
        self, request_id: str, method: str, title: str, data: dict
    ) -> None:
        """Show a Qt dialog for a pi ``extension_ui_request`` and send the
        response back through the bridge."""
        response: dict

        if method == "confirm":
            message = str(data.get("message", ""))
            reply = QMessageBox.question(
                self, title, message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            response = {"confirmed": reply == QMessageBox.StandardButton.Yes}

        elif method == "select":
            options_raw = data.get("options", [])
            options = (
                [str(o) for o in options_raw]
                if isinstance(options_raw, list) else []
            )
            item, ok = QInputDialog.getItem(
                self, title, "Choose:", options, 0, False,
            )
            if ok:
                response = {"value": item}
            else:
                response = {"cancelled": True}

        elif method == "input":
            placeholder = str(data.get("placeholder", ""))
            text, ok = QInputDialog.getText(self, title, placeholder)
            if ok:
                response = {"value": text}
            else:
                response = {"cancelled": True}

        elif method == "editor":
            prefill = str(data.get("prefill", ""))
            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            dlg.resize(500, 400)
            layout = QVBoxLayout(dlg)
            editor = QTextEdit()
            editor.setPlainText(prefill)
            layout.addWidget(editor)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
            )
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                response = {"value": editor.toPlainText()}
            else:
                response = {"cancelled": True}

        else:
            return  # unknown method, don't respond

        self._bridge.send_extension_ui_response(request_id, response)

    def _on_extension_ui_notify(self, message: str, notify_type: str) -> None:
        # Log to stderr for now; future: status bar or toast.
        print(
            f"[notify] [{notify_type}] {message}",
            flush=True,
        )

    def _on_extension_ui_status(self, key: str, text: str) -> None:
        """Handle a setStatus extension_ui_request.

        When *text* is non-empty, store/update the entry for *key*.
        When *text* is empty, remove the entry (status was cleared).
        """
        if text:
            self._status_entries[key] = text
        else:
            self._status_entries.pop(key, None)
        self._update_status_extras()

    def _update_status_extras(self) -> None:
        """Rebuild the status extras label from current entries.

        Shows all non-empty status lines joined with spaces on a second
        row of the status bar.  Hidden when there are no entries.
        """
        parts = [v for v in self._status_entries.values() if v]
        if not parts:
            self._status_extras_label.setVisible(False)
            return
        self._status_extras_label.setText("    ".join(parts))
        self._status_extras_label.setVisible(True)

    # ── slots: status bar ────────────────────────────────────────

    def _on_response_received(self, command: str, response: object) -> None:
        """Update status labels from get_state / get_session_stats responses."""
        if not isinstance(response, dict):
            return
        if not response.get("success"):
            return
        data = response.get("data")
        if not isinstance(data, dict):
            return

        if command == "get_state":
            model = data.get("model")
            if isinstance(model, dict):
                self._provider = str(model.get("provider", ""))
                thinking_level = str(data.get("thinkingLevel", ""))
                self._thinking_level = thinking_level
                model_name = model.get("name") or model.get("id") or "?"
                parts: list[str] = []
                if self._provider:
                    parts.append(f"({self._provider})")
                parts.append(model_name)
                if thinking_level:
                    parts.append("•")
                    parts.append(thinking_level)
                self._model_label.setText(" ".join(parts))
        elif command == "get_session_stats":
            tokens = data.get("tokens")
            if isinstance(tokens, dict):
                inp = int(tokens.get("input", 0) or 0)
                out = int(tokens.get("output", 0) or 0)
                cache = int(tokens.get("cacheRead", 0) or 0)
                parts: list[str] = []
                if inp:
                    parts.append(f"↑{_fmt_tokens(inp)}")
                if out:
                    parts.append(f"↓{_fmt_tokens(out)}")
                if cache:
                    parts.append(f"R{_fmt_tokens(cache)}")
                if parts:
                    self._tokens_label.setText(" ".join(parts))
                else:
                    self._tokens_label.setText("")
            ctx = data.get("contextUsage")
            if isinstance(ctx, dict) and ctx.get("contextWindow"):
                pct = ctx.get("percent")
                if pct is not None:
                    self._context_label.setText(f"{float(pct):.0f}%")
                else:
                    self._context_label.setText("")
            else:
                self._context_label.setText("")

    def _refresh_status_bar(self) -> None:
        """Request fresh state and stats from pi; update local info."""
        self._update_path_label()
        self._bridge.send_command({"type": "get_state"})
        self._bridge.send_command({"type": "get_session_stats"})

    def _update_path_label(self) -> None:
        """Update the path label with shortened cwd and optional git branch."""
        cwd = Path.cwd()
        home = Path.home()
        try:
            short = f"~/{cwd.relative_to(home)}" if cwd.is_relative_to(home) else str(cwd)
        except ValueError:
            short = str(cwd)
        branch = _git_branch(cwd)
        if branch:
            self._path_label.setText(f"{short} ({branch})")
        else:
            self._path_label.setText(short)


# ── helpers ──────────────────────────────────────────────────────────


def _git_branch(cwd: Path) -> str:
    """Return the current git branch name, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=2,
        )
        branch = result.stdout.strip()
        if result.returncode == 0 and branch and branch != "HEAD":
            return branch
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return ""


def _fmt_tokens(count: int) -> str:
    """Format a token count with k / M suffix."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)
