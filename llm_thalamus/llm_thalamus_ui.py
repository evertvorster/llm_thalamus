#!/usr/bin/env python3
"""
llm_thalamus_ui – PySide6 UI for the llm_thalamus controller.

- Uses BASE_DIR / sys.path so we can just `import llm_thalamus`.
- Thalamus + LLM are now run in a background thread via ThalamusWorker.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

from ui_config_dialog import ConfigDialog

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWebEngineWidgets import QWebEngineView
from ui.widgets import BrainWidget, StatusLight, ChatInput, ThalamusLogWindow

from thalamus_worker import ThalamusWorker
import queue

import ui_chat_renderer
import ui_spaces
import spaces_manager

# ---------------------------------------------------------------------------
# Paths & config helpers
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from paths import get_user_config_path, get_chat_history_dir, get_log_dir  # noqa: E402

# Resolve per-environment paths (dev tree vs installed)
CHAT_HISTORY_DIR = get_chat_history_dir()
LOG_DIR = get_log_dir()
CONFIG_PATH = get_user_config_path()


def ensure_directories():
    """
    Ensure that all key directories exist.

    In dev mode this stays inside the repo.
    When installed, this uses XDG-style locations via paths.py.
    """
    _ = CHAT_HISTORY_DIR
    _ = LOG_DIR
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """
    Load the main JSON config file. If missing or unreadable, fall back
    to a minimal UI+logging config so the UI can still start.
    """
    ensure_directories()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Minimal default; other sections (thalamus, embeddings, etc.) can be
    # added by hand or via future config UI.
    return {
        "logging": {
            "thalamus_enabled": False
        },
        "ui": {
            "auto_connect_thalamus": True,
            "show_previous_session_on_startup": True,
        },
    }


def save_config(cfg: dict):
    """
    Persist the merged config back to disk. Whatever dict the ConfigDialog
    gives us is written as-is, so existing top-level sections are preserved.
    """
    ensure_directories()
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("llm-thalamus UI")
        self.resize(1100, 700)

        self.config = config
        self.session_id = self._new_session_id()
        self.chat_file = None
        self.thalamus_log_file = None
        self.thalamus_log_window: ThalamusLogWindow | None = None

        # In-memory message list used by the rendered chat view
        # Each entry: {"role": "user"/"assistant", "content": str, "meta": str}
        self.chat_messages = []

        # Brain status flags (drive the glowing brain)
        self._thalamus_active = False
        self._llm_active = False
        self.brain_widget: BrainWidget | None = None

        ensure_directories()
        self._open_chat_file()
        self._open_thalamus_log_if_enabled()

        # Worker that owns Thalamus + LLM on a background thread
        self.worker: ThalamusWorker | None = ThalamusWorker()

        # UI
        self._build_ui()

        if self.config.get("ui", {}).get("show_previous_session_on_startup", True):
            self._load_previous_session_chat()

        # initial statuses
        self._set_thalamus_status("disconnected")
        self._set_llm_status("disconnected")
        self._set_memory_status("disconnected")

        # Event pump from worker → UI
        self.event_timer = QtCore.QTimer(self)
        self.event_timer.setInterval(30)  # ~33 fps
        self.event_timer.timeout.connect(self._drain_worker_events)
        self.event_timer.start()

        # Start worker thread immediately
        if self.worker:
            self.worker.start()

        # Send disabled until worker reports ready
        self._update_send_enabled(False)

    # ------------------------------------------------------------------ UI build

    def _build_ui(self):
        central = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        # Top dashboard (currently empty, reserved for future controls)
        dashboard = self._build_dashboard()
        root_layout.addWidget(dashboard, 0)

        # Main area: chat panel (left) + spaces panel (right), inside a splitter
        chat_widget = self._build_chat_panel()
        self.spaces_panel = ui_spaces.SpacesPanel(parent=central)

        # Create the brain widget and put it into the brain placeholder
        self.brain_widget = BrainWidget(parent=self.spaces_panel.brain_placeholder)
        self.brain_widget.clicked.connect(self._toggle_thalamus_pane)

        ph_layout = self.spaces_panel.brain_placeholder.layout()
        if ph_layout is not None:
            # Remove any placeholder items (stretches, labels, etc.)
            while ph_layout.count():
                item = ph_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            ph_layout.addWidget(self.brain_widget)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, central)
        splitter.addWidget(chat_widget)
        splitter.addWidget(self.spaces_panel)

        # Chat gets more space by default, but both are resizable
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

    def _build_dashboard(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(10)

        # Reserved for future controls; the glowing brain lives
        # in the SpacesPanel's brain_placeholder instead.
        layout.addStretch(1)

        return container

    def _build_chat_panel(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # View toggle: rendered (default) / raw
        view_mode_layout = QtWidgets.QHBoxLayout()
        view_mode_layout.setContentsMargins(0, 0, 0, 0)

        self.view_toggle = QtWidgets.QPushButton()
        self.view_toggle.setCheckable(True)
        self.view_toggle.setChecked(True)  # rendered by default
        self.view_toggle.setText("View: Rendered")
        self.view_toggle.clicked.connect(self._on_view_mode_changed)

        view_mode_layout.addWidget(self.view_toggle)
        view_mode_layout.addStretch(1)

        # Chat displays: rendered (WebEngine) and raw (plain text)
        self.chat_raw_display = QtWidgets.QPlainTextEdit()
        self.chat_raw_display.setReadOnly(True)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.chat_raw_display.setFont(mono_font)

        self.chat_render_view = QWebEngineView()
        self.chat_render_view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        self.chat_stack = QtWidgets.QStackedWidget()
        self.chat_stack.addWidget(self.chat_render_view)   # index 0: rendered
        self.chat_stack.addWidget(self.chat_raw_display)   # index 1: raw
        self.chat_stack.setCurrentIndex(0)

        # Input row
        input_row = QtWidgets.QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send_clicked)

        buttons_col = QtWidgets.QVBoxLayout()
        buttons_col.setContentsMargins(4, 0, 0, 0)
        buttons_col.setSpacing(4)

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)

        self.config_button = QtWidgets.QPushButton("Config")
        self.config_button.clicked.connect(self._on_config_clicked)

        self.quit_button = QtWidgets.QPushButton("Quit")
        self.quit_button.clicked.connect(QtWidgets.QApplication.quit)

        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.config_button)
        buttons_col.addWidget(self.quit_button)
        buttons_col.addStretch(1)

        input_row.addWidget(self.chat_input, 1)
        input_row.addLayout(buttons_col, 0)

        # Wrap the input row in its own widget so we can put it in a splitter
        input_container = QtWidgets.QWidget()
        input_container.setLayout(input_row)
        input_container.setMinimumHeight(80)  # tweak if you want more/less

        # Splitter between chat history (top) and input area (bottom)
        chat_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, container)
        chat_splitter.addWidget(self.chat_stack)
        chat_splitter.addWidget(input_container)
        chat_splitter.setStretchFactor(0, 4)  # chat gets more space
        chat_splitter.setStretchFactor(1, 1)  # input is resizable

        layout.addLayout(view_mode_layout, 0)
        layout.addWidget(chat_splitter, 1)

        return container

    # ------------------------------------------------------------------ Status helpers

    def _update_brain_graphic(self) -> None:
        """
        Map the boolean flags into one of three visual states.
        """
        if not self.brain_widget:
            return

        if not self._thalamus_active:
            state = "inactive"
        elif not self._llm_active:
            state = "thalamus"
        else:
            state = "llm"

        self.brain_widget.set_state(state)

    def _set_llm_status(self, status: str):
        """
        LLM on/off signal → brain full glow and Send-button rate limiting.

        The worker sends:
        - ("status", "llm", "busy", None) before processing
        - ("status", "llm", "idle", None) after processing

        So:
        - busy      -> full brain, Send disabled
        - idle      -> thalamus-only brain, Send re-enabled (if worker is ready)
        - connected -> treat like idle for Send enabling
        - other     -> brain off, Send disabled
        """
        # Brain animation state
        self._llm_active = (status == "busy")
        self._update_brain_graphic()

        # Rate limiting: disable Send while the LLM is thinking
        if status == "busy":
            # LLM working → do not allow new messages
            self._update_send_enabled(False)
        elif status in ("connected", "idle"):
            # LLM is available again; only enable Send if the worker is ready
            ready = bool(self.worker and self.worker.ready)
            self._update_send_enabled(ready)
        else:
            # Disconnected/error → keep Send disabled
            self._update_send_enabled(False)

    def _set_thalamus_status(self, status: str):
        """
        Thalamus on/off signal → brainstem/thalamus glow.
        Also controls whether the send button is enabled.
        """
        self._thalamus_active = status in ("connected", "busy", "idle")
        ready = bool(self.worker and self.worker.ready)
        self._update_send_enabled(self._thalamus_active and ready)
        self._update_brain_graphic()

    def _set_memory_status(self, status: str):
        """
        Memory status is no longer visualised; keep as a no-op hook
        in case the engine still emits memory events.
        """
        pass

    def _update_send_enabled(self, enabled: bool):
        self.send_button.setEnabled(bool(enabled))

    # ------------------------------------------------------------------ Chat history

    def _new_session_id(self) -> str:
        return datetime.now().strftime("%Y%m%dT%H%M%S")

    def _open_chat_file(self):
        filename = f"session-{self.session_id}.log"
        self.chat_file_path = CHAT_HISTORY_DIR / filename
        self.chat_file = self.chat_file_path.open("a", encoding="utf-8")

    def _open_thalamus_log_if_enabled(self):
        if self.config.get("logging", {}).get("thalamus_enabled", False):
            filename = f"thalamus-{self.session_id}.log"
            self.thalamus_log_path = LOG_DIR / filename
            self.thalamus_log_file = self.thalamus_log_path.open("a", encoding="utf-8")
        else:
            self.thalamus_log_path = None
            self.thalamus_log_file = None

    def _load_previous_session_chat(self):
        files = sorted(
            CHAT_HISTORY_DIR.glob("session-*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return

        last_file = None
        current_name = f"session-{self.session_id}.log"
        for f in files:
            if f.name != current_name:
                last_file = f
                break

        if last_file is None:
            return

        try:
            with last_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return

        if lines:
            header = f"--- Previous session: {last_file.name} ---"
            self.chat_raw_display.appendPlainText(header)
            self.chat_messages.append({
                "role": "assistant",
                "content": header,
                "meta": "previous session",
            })

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    role = record.get("role", "assistant")
                    content = record.get("content", "")
                    self._append_chat_to_display(role, content, is_historical=True)
                except Exception:
                    self.chat_raw_display.appendPlainText(line)
                    self.chat_messages.append({
                        "role": "assistant",
                        "content": line,
                        "meta": "previous session",
                    })

            footer = "--- End of previous session ---"
            self.chat_raw_display.appendPlainText(footer + "\n")
            self.chat_messages.append({
                "role": "assistant",
                "content": footer,
                "meta": "previous session",
            })
            self._refresh_rendered_view()

    def _append_chat_to_display(self, role: str, content: str, is_historical: bool):
        prefix = "You: " if role == "user" else "Assistant: "
        text = f"{prefix}{content}"
        self.chat_raw_display.appendPlainText(text)

        meta = "previous session" if is_historical else ""
        self.chat_messages.append({
            "role": role,
            "content": content,
            "meta": meta,
        })
        self._refresh_rendered_view()

    def _write_chat_record(self, role: str, content: str):
        if not self.chat_file:
            return
        record = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "role": role,
            "content": content,
        }
        try:
            self.chat_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.chat_file.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------ Chat theming helpers

    def _build_chat_theme(self) -> dict:
        """
        Build a small, stable theme dict for the chat renderer
        based on the current Qt palette.

        This does NOT change any behaviour yet; it will be passed
        into ui_chat_renderer.render_chat_html() in a later step.
        """
        pal = self.palette()

        base = pal.color(QtGui.QPalette.Base)
        text = pal.color(QtGui.QPalette.Text)
        mid = pal.color(QtGui.QPalette.Mid)

        # Helper: Qt QColor -> "#rrggbb"
        def to_css(c: QtGui.QColor) -> str:
            return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"

        # Derive bubble backgrounds from the base colour so they follow
        # whatever theme (light/dark/custom) the user is running.
        user_bg = base.lighter(108)       # slightly lighter than base
        assistant_bg = base               # same as base for now
        border = mid

        return {
            "bg": to_css(base),
            "text": to_css(text),
            "bubble_user": to_css(user_bg),
            "bubble_assistant": to_css(assistant_bg),
            "meta_text": to_css(mid),
            "border": to_css(border),
        }

    def _refresh_rendered_view(self):
        """Rebuild the rendered chat view from in-memory messages."""
        try:
            theme = self._build_chat_theme()
            html = ui_chat_renderer.render_chat_html(self.chat_messages, theme=theme)
            self.chat_render_view.setHtml(html, QtCore.QUrl("file:///"))
        except Exception:
            # Don't crash the UI if rendering fails for some reason.
            pass

    # ------------------------------------------------------------------ Thalamus pane logging

    def _append_thalamus_text(self, text: str):
        if self.thalamus_log_window is None:
            self.thalamus_log_window = ThalamusLogWindow(self, self.session_id)
        self.thalamus_log_window.append_line(text)

        if self.thalamus_log_file is not None:
            try:
                self.thalamus_log_file.write(text + "\n")
                self.thalamus_log_file.flush()
            except Exception:
                pass

    # ------------------------------------------------------------------ Config handling

    def _on_config_clicked(self):
        dlg = ConfigDialog(self.config, self)
        dlg.configApplied.connect(self._on_config_applied)
        dlg.exec()

    @QtCore.Slot(dict, bool)
    def _on_config_applied(self, new_config: dict, restart_thalamus: bool):
        self.config = new_config
        save_config(self.config)

        new_enabled = self.config.get("logging", {}).get("thalamus_enabled", False)
        currently_enabled = self.thalamus_log_file is not None

        if new_enabled and not currently_enabled:
            self._open_thalamus_log_if_enabled()
        elif not new_enabled and currently_enabled:
            try:
                self.thalamus_log_file.close()
            except Exception:
                pass
            self.thalamus_log_file = None
            self.thalamus_log_path = None

        if restart_thalamus:
            self.restart_thalamus()

    def restart_thalamus(self):
        # Stop existing worker, create a new one so it picks up new config
        if self.worker:
            try:
                self.worker.stop()
            except Exception:
                pass
            self.worker = None

        self._set_thalamus_status("disconnected")
        self._set_llm_status("disconnected")
        self._set_memory_status("disconnected")
        self._update_send_enabled(False)

        self._append_thalamus_text("Restarting Thalamus with new configuration...")

        self.worker = ThalamusWorker()
        self.worker.start()

    # ------------------------------------------------------------------ Worker event pump

    def _drain_worker_events(self):
        """Pull events from the worker's queue and handle them in the UI thread."""
        if not self.worker:
            return

        while True:
            try:
                evt = self.worker.event_queue.get_nowait()
            except queue.Empty:
                break

            kind, *payload = evt

            if kind == "internal_ready":
                # Thalamus successfully constructed in worker
                self._append_thalamus_text("Thalamus initialised and connected (worker).")
                self._set_thalamus_status("connected")
                self._update_send_enabled(True)

            elif kind == "internal_error":
                (msg,) = payload
                self._append_thalamus_text(f"Thalamus worker error: {msg}")
                self._set_thalamus_status("error")
                self._update_send_enabled(False)

            elif kind == "chat":
                role, content = payload
                # Ignore echoed user messages; we already add them in _on_send_clicked
                if role != "user":
                    self._append_chat_to_display(role, content, is_historical=False)
                    self._write_chat_record(role, content)

            elif kind == "status":
                subsystem, status, detail = payload
                self.handle_status_update_event(subsystem, status, detail)

            elif kind == "control":
                label, text = payload
                self.handle_thalamus_control_entry_event(label, text)

            elif kind == "session_started":
                self.handle_session_started()

            elif kind == "session_ended":
                self.handle_session_ended()

    # ------------------------------------------------------------------ Event hooks (UI-level)

    def handle_status_update_event(self, subsystem: str, status: str, detail: str | None = None):
        if subsystem == "thalamus":
            self._set_thalamus_status(status)
        elif subsystem == "llm":
            self._set_llm_status(status)
        elif subsystem == "memory":
            self._set_memory_status(status)

    def handle_thalamus_control_entry_event(self, label: str, raw_text: str):
        header = f"[{label}]"
        self._append_thalamus_text(header)
        self._append_thalamus_text(raw_text)
        self._append_thalamus_text("")

    def handle_session_started(self):
        pass

    def handle_session_ended(self):
        pass

    # ------------------------------------------------------------------ UI events

    @QtCore.Slot(bool)
    def _on_view_mode_changed(self, checked: bool):
        """Toggle between rendered (default) and raw views."""
        if checked:
            self.view_toggle.setText("View: Rendered")
            self.chat_stack.setCurrentWidget(self.chat_render_view)
        else:
            self.view_toggle.setText("View: Raw")
            self.chat_stack.setCurrentWidget(self.chat_raw_display)

    @QtCore.Slot()
    def _on_send_clicked(self):
        if not self.send_button.isEnabled():
            return
        if not self.worker or not self.worker.ready:
            return

        content = self.chat_input.toPlainText().strip()
        if not content:
            return

        # Show the user's message immediately in the UI + log
        self._append_chat_to_display("user", content, is_historical=False)
        self._write_chat_record("user", content)

        # Clear input after updating UI
        self.chat_input.clear()

        # Ask Spaces which documents are currently active.
        # We reuse the existing helper that already returns
        # [{"name": ..., "text": ...}, ...]
        doc_list = None
        try:
            manager = spaces_manager.get_manager()
            doc_list = manager.get_active_documents_for_prompt()
        except Exception:
            # If anything goes wrong, just continue without docs.
            doc_list = None

        # Push the message (and any active docs) to the worker thread
        if doc_list is not None:
            self.worker.submit_user_message(content, doc_list)
        else:
            self.worker.submit_user_message(content)

    # ------------------------------------------------------------------ Log window toggling

    def _toggle_thalamus_pane(self):
        """
        Show or hide the separate Thalamus log window.

        This replaces the old dock-based approach so we don't interfere
        with tiling window managers by resizing the main window.
        """
        if self.thalamus_log_window is None:
            self.thalamus_log_window = ThalamusLogWindow(self, self.session_id)

        if self.thalamus_log_window.isVisible():
            self.thalamus_log_window.hide()
        else:
            self.thalamus_log_window.show()
            self.thalamus_log_window.raise_()
            self.thalamus_log_window.activateWindow()

    # ------------------------------------------------------------------ Cleanup

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            if self.chat_file:
                self.chat_file.close()
        except Exception:
            pass

        try:
            if self.thalamus_log_file:
                self.thalamus_log_file.close()
        except Exception:
            pass

        if self.worker:
            try:
                self.worker.stop()
            except Exception:
                pass

        self._thalamus_active = False
        self._llm_active = False
        self._update_brain_graphic()

        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    config = load_config()
    win = MainWindow(config=config)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
