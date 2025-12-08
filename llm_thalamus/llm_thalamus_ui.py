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

from thalamus_worker import ThalamusWorker
import queue

import ui_chat_renderer
import ui_spaces

# ---------------------------------------------------------------------------
# Paths & config helpers
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

CHAT_HISTORY_DIR = BASE_DIR / "chat_history"
LOG_DIR = BASE_DIR / "log"
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"


def ensure_directories():
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    ensure_directories()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    cfg = {
        "logging": {
            "thalamus_enabled": False
        },
        "ui": {
            "auto_connect_thalamus": True,
            "show_previous_session_on_startup": True
        }
    }
    return cfg


def save_config(cfg: dict):
    ensure_directories()
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Small helper widgets
# ---------------------------------------------------------------------------

class StatusLight(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._status = "disconnected"

        self.indicator = QtWidgets.QLabel()
        self.indicator.setFixedSize(14, 14)

        self.text_label = QtWidgets.QLabel(label)
        font = self.text_label.font()
        font.setPointSize(font.pointSize() - 1)
        self.text_label.setFont(font)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        layout.addWidget(self.indicator, 0, QtCore.Qt.AlignVCenter)
        layout.addWidget(self.text_label, 0, QtCore.Qt.AlignVCenter)

        self.setStatus("disconnected")

    def setStatus(self, status: str):
        self._status = status
        color = "#6c757d"
        if status == "disconnected":
            color = "#6c757d"
        elif status in ("connected", "idle"):
            color = "#198754"
        elif status == "busy":
            color = "#0d6efd"
        elif status == "error":
            color = "#dc3545"
        self.indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;"
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ChatInput(QtWidgets.QTextEdit):
    sendRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.setFont(font)
        self.setPlaceholderText("Type your message...")

        # Track current font size so Ctrl+wheel can adjust it
        self._font_size = self.font().pointSizeF() or 12.0

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        # Ctrl + mouse wheel = change font size (like terminals do)
        if event.modifiers() & QtCore.Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 1.0  # points per notch

            if delta > 0:
                self._font_size += step
            elif delta < 0:
                self._font_size -= step

            # Clamp to something sensible
            self._font_size = max(8.0, min(self._font_size, 32.0))
            self._apply_font_size()
            # Don't scroll the text when zooming
            return

        # Normal wheel behaviour when Ctrl is not held
        super().wheelEvent(event)

    def _apply_font_size(self) -> None:
        font = self.font()
        font.setPointSizeF(self._font_size)
        self.setFont(font)



# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("llm-thalamus UI")
        self.resize(1100, 700)

        # Remember base geometry for expanding/collapsing thalamus pane
        self._collapsed_geometry = None
        self._expanded_geometry = None  

        self.config = config
        self.session_id = self._new_session_id()
        self.chat_file = None
        self.thalamus_log_file = None

        # In-memory message list used by the rendered chat view
        # Each entry: {"role": "user"/"assistant", "content": str, "meta": str}
        self.chat_messages = []

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

        # Top dashboard (status lights)
        dashboard = self._build_dashboard()
        root_layout.addWidget(dashboard, 0)

        # Main area: chat panel (left) + spaces panel (right)
        main_area = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        chat_widget = self._build_chat_panel()

        # NEW: Spaces panel with brain placeholder on the right
        self.spaces_panel = ui_spaces.SpacesPanel(parent=main_area)

        main_layout.addWidget(chat_widget, 1)
        main_layout.addWidget(self.spaces_panel, 0)

        root_layout.addWidget(main_area, 1)

        self.setCentralWidget(central)
        self._build_thalamus_dock()

    def _build_dashboard(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(10)

        self.llm_light = StatusLight("LLM")
        self.thalamus_light = StatusLight("Thalamus")
        self.memory_light = StatusLight("Memory")

        self.thalamus_light.clicked.connect(self._toggle_thalamus_pane)

        layout.addWidget(self.llm_light, 0, QtCore.Qt.AlignLeft)
        layout.addWidget(self.thalamus_light, 0, QtCore.Qt.AlignLeft)
        layout.addWidget(self.memory_light, 0, QtCore.Qt.AlignLeft)
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

        layout.addLayout(view_mode_layout, 0)
        layout.addWidget(self.chat_stack, 1)
        layout.addLayout(input_row, 0)

        return container

    def _build_thalamus_dock(self):
        self.thalamus_dock = QtWidgets.QDockWidget("Thalamus Control", self)
        self.thalamus_dock.setAllowedAreas(
            QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea
        )

        inner = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(inner)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        self.thalamus_text = QtWidgets.QPlainTextEdit()
        self.thalamus_text.setReadOnly(True)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.thalamus_text.setFont(mono_font)

        save_button = QtWidgets.QPushButton("Save Thalamus Log…")
        save_button.clicked.connect(self._on_save_thalamus_clicked)

        vbox.addWidget(self.thalamus_text, 1)
        vbox.addWidget(save_button, 0, QtCore.Qt.AlignRight)

        self.thalamus_dock.setWidget(inner)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.thalamus_dock)
        self.thalamus_dock.hide()

    # ------------------------------------------------------------------ Status helpers

    def _set_llm_status(self, status: str):
        self.llm_light.setStatus(status)

    def _set_thalamus_status(self, status: str):
        self.thalamus_light.setStatus(status)
        # Enable send only when Thalamus is usable and worker is ready
        ready = bool(self.worker and self.worker.ready)
        self._update_send_enabled(status in ("connected", "busy", "idle") and ready)

    def _set_memory_status(self, status: str):
        self.memory_light.setStatus(status)

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

    def _refresh_rendered_view(self):
        """Rebuild the rendered chat view from in-memory messages."""
        try:
            html = ui_chat_renderer.render_chat_html(self.chat_messages)
            self.chat_render_view.setHtml(html)
        except Exception:
            # Don't crash the UI if rendering fails for some reason.
            pass

    # ------------------------------------------------------------------ Thalamus pane logging

    def _append_thalamus_text(self, text: str):
        self.thalamus_text.appendPlainText(text)
        if self.thalamus_log_file is not None:
            try:
                self.thalamus_log_file.write(text + "\n")
                self.thalamus_log_file.flush()
            except Exception:
                pass

    def _on_save_thalamus_clicked(self):
        default_name = f"thalamus-manual-{self.session_id}.log"
        initial_path = str(LOG_DIR / default_name)

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Thalamus Log",
            initial_path,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.thalamus_text.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Failed to save log:\n{e}"
            )

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

        # Push the message to the worker thread
        self.worker.submit_user_message(content)

    # ------------------------------------------------------------------ Dock toggling

    def _toggle_thalamus_pane(self):
        """Show/hide the Thalamus log dock.

        When shown:
            - Window width doubles (Wayland-friendly)
            - The vertical divider between chat and log is placed exactly in the middle
            (i.e. both take 50% width).
        When hidden:
            - Restore original window width
            - Release width constraint.
        """

        if self.thalamus_dock.isVisible():
            # Collapse: hide and restore width
            self.thalamus_dock.hide()
            self.thalamus_dock.setFixedWidth(0)   # release width lock

            if getattr(self, "_collapsed_geometry", None) is not None:
                g = self._collapsed_geometry
                self.resize(g.width(), g.height())

        else:
            # Expand: remember geometry, then double width
            g = self.geometry()
            self._collapsed_geometry = g

            new_width = g.width() * 2
            self.resize(new_width, g.height())

            # Show the dock BEFORE sizing it
            self.thalamus_dock.show()

            # Now set dock width to exactly half of the main window
            half_width = self.width() // 2
            self.thalamus_dock.setFixedWidth(half_width)

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

        super().closeEvent(event)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    config = load_config()
    win = MainWindow(config=config)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
