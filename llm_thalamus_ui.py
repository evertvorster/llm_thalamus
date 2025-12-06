#!/usr/bin/env python3
"""
llm_thalamus_ui – PySide6 UI for the llm_thalamus controller.

- Uses BASE_DIR / sys.path so we can just `import llm_thalamus`.
- On startup, it tries to import and instantiate Thalamus.
"""

import os
import sys
import json
import importlib
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

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

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Config dialog
# ---------------------------------------------------------------------------

class ConfigDialog(QtWidgets.QDialog):
    configApplied = QtCore.Signal(dict, bool)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thalamus Configuration")
        self.setModal(True)
        self._config = json.loads(json.dumps(config))

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self.thalamus_logging_checkbox = QtWidgets.QCheckBox(
            "Enable thalamus logging (per-session log files)"
        )
        form.addRow("Thalamus logging:", self.thalamus_logging_checkbox)

        layout.addLayout(form)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self.save_button = QtWidgets.QPushButton("Save")
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.close_button = QtWidgets.QPushButton("Close")

        self.save_button.clicked.connect(self._on_save_clicked)
        self.apply_button.clicked.connect(self._on_apply_clicked)
        self.close_button.clicked.connect(self.reject)

        btn_row.addWidget(self.save_button)
        btn_row.addWidget(self.apply_button)
        btn_row.addWidget(self.close_button)

        layout.addLayout(btn_row)

    def _load_values(self):
        logging_cfg = self._config.get("logging", {})
        self.thalamus_logging_checkbox.setChecked(
            bool(logging_cfg.get("thalamus_enabled", False))
        )

    def _apply_changes_to_config(self):
        self._config.setdefault("logging", {})
        self._config["logging"]["thalamus_enabled"] = self.thalamus_logging_checkbox.isChecked()

    def _on_save_clicked(self):
        self._apply_changes_to_config()
        self.configApplied.emit(self._config, True)
        self.accept()

    def _on_apply_clicked(self):
        self._apply_changes_to_config()
        self.configApplied.emit(self._config, True)


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
        self.thalamus = None

        ensure_directories()
        self._open_chat_file()
        self._open_thalamus_log_if_enabled()

        self._build_ui()

        if self.config.get("ui", {}).get("show_previous_session_on_startup", True):
            self._load_previous_session_chat()

        self._set_thalamus_status("disconnected")
        self._set_llm_status("disconnected")
        self._set_memory_status("disconnected")

        if self.config.get("ui", {}).get("auto_connect_thalamus", True):
            self._init_thalamus()

        self._update_send_enabled(self.thalamus is not None)

    # ------------------------------------------------------------------ UI build

    def _build_ui(self):
        central = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        dashboard = self._build_dashboard()
        root_layout.addWidget(dashboard, 0)

        chat_widget = self._build_chat_panel()
        root_layout.addWidget(chat_widget, 1)

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

        view_mode_layout = QtWidgets.QHBoxLayout()
        view_mode_layout.setContentsMargins(0, 0, 0, 0)

        view_mode_label = QtWidgets.QLabel("View:")
        self.raw_radio = QtWidgets.QRadioButton("Raw")
        self.rendered_radio = QtWidgets.QRadioButton("Rendered")
        self.raw_radio.setChecked(True)
        self.raw_radio.toggled.connect(self._on_view_mode_changed)

        view_mode_layout.addWidget(view_mode_label)
        view_mode_layout.addWidget(self.raw_radio)
        view_mode_layout.addWidget(self.rendered_radio)
        view_mode_layout.addStretch(1)

        self.chat_display = QtWidgets.QPlainTextEdit()
        self.chat_display.setReadOnly(True)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.chat_display.setFont(mono_font)

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
        layout.addWidget(self.chat_display, 1)
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
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.thalamus_dock)
        self.thalamus_dock.hide()

    # ------------------------------------------------------------------ Thalamus wiring

    def _init_thalamus(self):
        """
        Simple version: just import llm_thalamus and instantiate Thalamus.
        """
        try:
            module = importlib.import_module("llm_thalamus")
            ThalamusClass = getattr(module, "Thalamus", None)
            if ThalamusClass is None:
                raise AttributeError("Thalamus class not found in llm_thalamus module")

            th = ThalamusClass()

            th.events.on_chat_message = self.handle_chat_message_event
            th.events.on_status_update = self.handle_status_update_event
            th.events.on_thalamus_control_entry = self.handle_thalamus_control_entry_event
            th.events.on_session_started = self.handle_session_started
            th.events.on_session_ended = self.handle_session_ended

            self.thalamus = th
            self._append_thalamus_text("Thalamus initialised and connected.")
            self._set_thalamus_status("connected")
            self._update_send_enabled(True)
        except Exception as e:
            self._append_thalamus_text(
                f"Failed to initialise Thalamus: {e}\n"
                "Check that llm_thalamus.py exists in the same directory, and imports cleanly."
            )
            self.thalamus = None
            self._set_thalamus_status("error")
            self._update_send_enabled(False)

    # ------------------------------------------------------------------ Status helpers

    def _set_llm_status(self, status: str):
        self.llm_light.setStatus(status)

    def _set_thalamus_status(self, status: str):
        self.thalamus_light.setStatus(status)
        self._update_send_enabled(status in ("connected", "busy", "idle") and self.thalamus)

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
            self.chat_display.appendPlainText(
                f"--- Previous session: {last_file.name} ---"
            )
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
                    self.chat_display.appendPlainText(line)
            self.chat_display.appendPlainText("--- End of previous session ---\n")

    def _append_chat_to_display(self, role: str, content: str, is_historical: bool):
        prefix = "You: " if role == "user" else "Assistant: "
        text = f"{prefix}{content}"
        self.chat_display.appendPlainText(text)

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
        if self.thalamus is not None:
            self.thalamus = None

        self._set_thalamus_status("disconnected")
        self._set_llm_status("disconnected")
        self._set_memory_status("disconnected")
        self._update_send_enabled(False)

        self._append_thalamus_text("Restarting Thalamus with new configuration...")
        self._init_thalamus()

    # ------------------------------------------------------------------ Event hooks from Thalamus

    @QtCore.Slot()
    def _on_view_mode_changed(self):
        # TODO: implement rendered view later
        pass

    @QtCore.Slot()
    def _on_send_clicked(self):
        if not self.send_button.isEnabled() or not self.thalamus:
            return

        content = self.chat_input.toPlainText().strip()
        if not content:
            return

        self.chat_input.clear()
        try:
            self.thalamus.process_user_message(content)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Thalamus error",
                f"An error occurred while processing the message:\n{e}",
            )

    def handle_chat_message_event(self, role: str, content: str):
        self._append_chat_to_display(role, content, is_historical=False)
        self._write_chat_record(role, content)

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

    # ------------------------------------------------------------------ Dock toggling

    def _toggle_thalamus_pane(self):
        if self.thalamus_dock.isVisible():
            self.thalamus_dock.hide()
        else:
            self.thalamus_dock.show()

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
