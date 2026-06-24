"""MainWindow — the central Qt window connecting PiRPCBridge signals to the UI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
from ui.widgets import BrainWidget, ChatInput, SessionListWidget


class MainWindow(QWidget):
    """A minimal Qt window connecting PiRPCBridge signals to ChatRenderer."""

    def __init__(self, bridge: PiRPCBridge, graphics_dir: Path):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._settings = QSettings("llm-thalamus", "llm-thalamus")
        geom = self._settings.value("window/geometry")
        if geom is not None:
            self.restoreGeometry(geom)

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

        self.new_session_button = QPushButton("New Session")
        self.new_session_button.clicked.connect(self._on_new_session)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(4)
        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.new_session_button)
        buttons_col.addWidget(self.quit_button)
        input_row.addLayout(buttons_col)

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

        # --- session list ---
        self.session_list = SessionListWidget()
        self.session_list.switch_requested.connect(self._on_switch_session)
        self.session_list.rename_requested.connect(self._on_rename_session)
        self.session_list.delete_requested.connect(self._on_delete_session)
        self.session_list.inspect_requested.connect(self._on_inspect_session)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.brain, 0, Qt.AlignHCenter)
        right_layout.addWidget(self.session_list, 1)

        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.addWidget(left_panel)
        self._splitter.addWidget(right_panel)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)

        # --- status bar ---
        self._status_entries: dict[str, str] = {}

        self._status_frame = QFrame()
        self._status_frame.setObjectName("statusFrame")
        self._status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._status_frame.setStyleSheet(
            "#statusFrame {"
            "  border-top: 1px solid #ccc; padding: 2px 6px; background: #f5f5f7;"
            "  font-size: 9pt;"
            "}"
            "#statusFrame QLabel { color: #444; }"
        )
        status_vlayout = QVBoxLayout(self._status_frame)
        status_vlayout.setContentsMargins(0, 0, 0, 0)
        status_vlayout.setSpacing(0)

        # ── row 1: path | tokens | context | model ─────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(6, 2, 6, 2)
        row1.setSpacing(16)

        self._path_label = QLabel("\u00a0")
        self._path_label.setToolTip("Working directory and git branch")
        row1.addWidget(self._path_label)
        row1.addStretch(1)

        self._tokens_label = QLabel("\u00a0")
        self._tokens_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._tokens_label.setToolTip("Input ↑ / Output ↓ tokens (k=thousands, M=millions) — R = cache reads")
        row1.addWidget(self._tokens_label)

        self._context_label = QLabel("\u00a0")
        self._context_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._context_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._context_label.setToolTip("Context window usage — current tokens / total window size")
        row1.addWidget(self._context_label)

        self._model_label = QLabel("-")
        self._model_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._model_label.setToolTip("Provider and model — thinking level")
        row1.addWidget(self._model_label)

        status_vlayout.addLayout(row1)

        # ── row 2: extension status (hidden until populated) ─
        self._status_extras_label = QLabel("")
        self._status_extras_label.setToolTip("Extension status indicators (MemPalace, Memory capture)")
        self._status_extras_label.setVisible(False)
        status_vlayout.addWidget(self._status_extras_label)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._splitter, 1)
        root.addWidget(self._status_frame)

        # --- wire signals ---
        bridge.assistant_stream_start.connect(self._on_stream_start)
        bridge.assistant_stream_delta.connect(self._on_stream_delta)
        bridge.assistant_stream_end.connect(self._on_stream_end)
        bridge.thinking_started.connect(self._on_thinking_started)
        bridge.thinking_delta.connect(self._on_thinking_delta)
        bridge.thinking_finished.connect(self._on_thinking_finished)
        bridge.tool_execution_start.connect(self._on_tool_start)
        bridge.tool_execution_update.connect(self._on_tool_update)
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

        # Batch history renders until all startup messages arrive.
        self._history_batch_pending: bool = False

        # Restore splitter state after it's been populated.
        sp = self._settings.value("splitter/state")
        if sp is not None:
            self._splitter.restoreState(sp)

        # Escape aborts the current agent operation.
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._escape_shortcut.activated.connect(self._on_escape)

        # Track current session path for the session list.
        self._current_session_path: str | None = None
        self._pending_rename: str | None = None
        self._session_dir_path: Path | None = None

    def closeEvent(self, event) -> None:
        """Save window layout before closing."""
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("splitter/state", self._splitter.saveState())
        self._bridge.shutdown()
        super().closeEvent(event)

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

    def _on_tool_update(self, call_id: str, partial_text: str) -> None:
        """Streaming progress from a running tool (e.g. subagent output)."""
        # Clean escaped JSON sequences so the text is readable.
        cleaned = partial_text.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", '"')
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_update",
            "tool_call_id": call_id,
            "partial_result": cleaned,
        })

    def _on_tool_end(self, call_id: str, name: str, result_text: str, is_error: bool, details: dict = None) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_result",
            "tool_call_id": call_id,
            "tool_name": name,
            "result": result_text,
            "ok": not is_error,
            "details": details,
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

    # ── slots: session management ──────────────────────────────

    def _on_new_session(self) -> None:
        """Ask the user where to start a fresh session.

        Pops up a native directory picker.  If a directory different from
        the current CWD is chosen, pi is restarted from that location because
        pi's CWD is fixed at process launch.
        """
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select working directory for new session",
            str(Path.cwd()),
        )
        if not dir_path:
            return  # user cancelled

        target = Path(dir_path).resolve()
        if target == Path.cwd().resolve():
            # Same directory — just start a new session via RPC.
            self._bridge.send_command({"type": "new_session"})
        else:
            # Different directory — restart pi from the new CWD.
            self._bridge.restart(cwd=str(target))
            self.chat.clear()
            self._current_session_path = None
            self._refresh_session_list()
            QTimer.singleShot(1200, self._refresh_status_bar)

    def _on_switch_session(self, session_path: str) -> None:
        """Switch to a different session and reload conversation."""
        self._bridge.send_command({
            "type": "switch_session",
            "sessionPath": session_path,
        })

    def _on_inspect_session(self, session_path: str) -> None:
        """Open a read-only dialog showing the session's messages."""
        from ui.chat_renderer import ChatRenderer

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Inspect: {Path(session_path).stem[:40]}")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)

        viewer = ChatRenderer()
        layout.addWidget(viewer, 1)

        btn_row = QHBoxLayout()
        switch_btn = QPushButton("Switch to this session")
        switch_btn.clicked.connect(lambda: (
            self._on_switch_session(session_path),
            dlg.accept(),
        ))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(switch_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Show the dialog immediately with placeholder text, then populate
        # asynchronously so the user sees the window before the (potentially
        # large) session file is parsed and rendered.
        viewer.begin_batch()
        viewer.add_turn("system", "Rendering session…")
        viewer.end_batch()
        dlg.show()
        QTimer.singleShot(0, lambda: self._populate_inspect(viewer, session_path, dlg))
        dlg.exec()

    def _populate_inspect(
        self,
        viewer: "ChatRenderer",
        session_path: str,
        dlg: QDialog,
    ) -> None:
        """Parse and render a session file into an already-visible dialog."""
        viewer.clear()  # remove placeholder
        try:
            viewer.begin_batch()
            with open(session_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {}) if isinstance(entry, dict) else None
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = []
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                parts.append(b.get("text", ""))
                        text = " ".join(parts)
                    else:
                        text = str(content) if content else ""
                    if not text:
                        continue
                    display_role = "human" if role == "user" else "you"
                    viewer.add_turn(display_role, text)
            viewer.end_batch()
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.warning(dlg, "Error", f"Failed to read session:\n{e}")

    def _on_rename_session(self, session_path: str, new_name: str) -> None:
        """Set the display name for a session."""
        if session_path == self._current_session_path:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": new_name,
            })
        else:
            # Switch first, then rename on the response handler.
            self._pending_rename = new_name
            self._bridge.send_command({
                "type": "switch_session",
                "sessionPath": session_path,
            })

    def _on_delete_session(self, paths: list[str]) -> None:
        """Delete one or more session files from disk."""
        failed: list[str] = []
        for session_path in paths:
            try:
                p = Path(session_path)
                if p.exists():
                    p.unlink()
            except OSError as e:
                failed.append(f"{Path(session_path).name}: {e}")
        self._refresh_session_list()
        if failed:
            QMessageBox.warning(
                self, "Error",
                f"Failed to delete {len(failed)} session(s):\n"
                + "\n".join(failed[:5])
            )

    def _on_session_switched(self) -> None:
        """Called after new_session or switch_session succeeds.

        Clears the chat, reloads history, and refreshes the
        session list.
        """
        self.chat.clear()
        self._bridge.load_history()
        self._refresh_session_list()
        self._refresh_status_bar()

        # If a rename was queued before the switch, send it now.
        if self._pending_rename:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": self._pending_rename,
            })
            self._pending_rename = None

    def _session_dir(self) -> Path | None:
        """Resolve the pi session storage directory.

        Returns None if we can't determine the location.
        """
        if self._session_dir_path is not None:
            return self._session_dir_path
        cfg = self._bridge._pi_config_dir
        if cfg:
            self._session_dir_path = Path(cfg) / "sessions"
        else:
            self._session_dir_path = Path.home() / ".pi" / "agent" / "sessions"
        if not self._session_dir_path.is_dir():
            self._session_dir_path = None
        return self._session_dir_path

    def _refresh_session_list(self) -> None:
        """Re-scan the session directory and update the list widget."""
        self.session_list.set_sessions(
            str(self._session_dir()) if self._session_dir() else None,
            self._current_session_path,
        )

    # ── slots: session management ──────────────────────────────

    def _on_get_state(self, data: dict) -> None:
        """Handle ``get_state`` response — update model and session info."""
        # Update current session path.
        session_file = data.get("sessionFile")
        if session_file:
            self._current_session_path = str(session_file)
            self.session_list.set_current_session(self._current_session_path)

        # Update model label.
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

    def _on_history_turn(self, role: str, content: str, _ts: str) -> None:
        # Map pi roles to chat renderer roles.
        # pi roles: "user", "assistant", "toolResult", "bashExecution"
        display_role = "human" if role == "user" else "you"
        self.chat.begin_batch()
        self.chat.add_turn(display_role, content)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _on_history_thinking(self, text: str, _ts: str) -> None:
        # History thinking bubbles start collapsed.
        self.chat.begin_batch()
        self.chat.add_thinking(text)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _flush_history_batch(self) -> None:
        """Render all accumulated history messages in one shot."""
        self._history_batch_pending = False
        self.chat.end_batch()

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
        """Route RPC responses to the appropriate handler."""
        if not isinstance(response, dict):
            return
        if not response.get("success"):
            return
        data = response.get("data")
        if not isinstance(data, dict):
            return

        if command == "get_state":
            self._on_get_state(data)
        elif command == "new_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "switch_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "set_session_name":
            self._refresh_session_list()
        elif command == "clone":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
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
                    self._tokens_label.setText("\u00a0")
            ctx = data.get("contextUsage")
            if isinstance(ctx, dict) and ctx.get("contextWindow"):
                pct = ctx.get("percent")
                if pct is not None:
                    self._context_label.setText(f"{float(pct):.0f}%")
                else:
                    self._context_label.setText("\u00a0")
            else:
                self._context_label.setText("\u00a0")

    def _refresh_status_bar(self) -> None:
        """Request fresh state and stats from pi; update local info."""
        self._update_path_label()
        self._refresh_session_list()
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
