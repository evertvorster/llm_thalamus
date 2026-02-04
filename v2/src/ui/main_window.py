from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Slot, Qt

from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog
from ui.widgets import BrainWidget, ThalamusLogWindow


class MainWindow(QWidget):
    def __init__(self, cfg, controller):
        super().__init__()
        self.setWindowTitle("llm_thalamus")

        self._cfg = cfg
        self._controller = controller

        # --- brain/log state ---
        self._thalamus_active = True
        self._llm_active = False
        self._log_window: ThalamusLogWindow | None = None
        self._session_id = str(int(time.time()))

        # --- build chat widget (left pane content) ---
        self.chat = ChatRenderer()
        self.input = QTextEdit()
        self.input.setFixedHeight(80)

        self.send_btn = QPushButton("Send")
        self.config_btn = QPushButton("Config")

        chat_buttons = QHBoxLayout()
        chat_buttons.addWidget(self.send_btn)
        chat_buttons.addWidget(self.config_btn)

        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(6)
        chat_layout.addWidget(self.chat, 1)
        chat_layout.addWidget(self.input, 0)
        chat_layout.addLayout(chat_buttons, 0)

        # --- right pane: blank "Spaces" placeholder for now ---
        self.spaces_panel = QFrame()
        self.spaces_panel.setFrameShape(QFrame.StyledPanel)
        self.spaces_panel.setMinimumWidth(220)

        spaces_layout = QVBoxLayout(self.spaces_panel)
        spaces_layout.setContentsMargins(10, 10, 10, 10)
        spaces_layout.addWidget(QLabel("Spaces (disabled for now)"), 0, Qt.AlignTop)
        spaces_layout.addStretch(1)

        # --- dashboard row (top) ---
        dashboard = QWidget()
        dash_layout = QHBoxLayout(dashboard)
        dash_layout.setContentsMargins(6, 6, 6, 6)
        dash_layout.setSpacing(10)

        self.brain_widget = BrainWidget(cfg.graphics_dir)
        self.brain_widget.setMinimumSize(140, 140)

        dash_layout.addWidget(self.brain_widget, 0)

        # Placeholder area (old UI used this space for extra dashboard widgets)
        dash_placeholder = QFrame()
        dash_placeholder.setFrameShape(QFrame.NoFrame)
        dash_layout.addWidget(dash_placeholder, 1)

        # --- main splitter (chat | spaces) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(chat_widget)
        splitter.addWidget(self.spaces_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # --- root layout ---
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(dashboard, 0)
        root.addWidget(splitter, 1)

        # wiring
        self.send_btn.clicked.connect(self._on_send)
        self.config_btn.clicked.connect(self._on_config)
        self.brain_widget.clicked.connect(self._on_brain_clicked)

        controller.assistant_message.connect(self._on_reply)
        controller.busy_changed.connect(self._on_busy)
        controller.error.connect(self._on_error)
        controller.log_line.connect(self._on_log_line)

        # historical turns
        controller.history_turn.connect(self._on_history_turn)

        # initial brain state
        self._update_brain_graphic()

        # load history once on startup
        controller.emit_history()

    # --- brain & log ---

    def _update_brain_graphic(self) -> None:
        if not self._thalamus_active:
            state = "inactive"
        elif not self._llm_active:
            state = "thalamus"
        else:
            state = "llm"
        self.brain_widget.set_state(state)

    @Slot()
    def _on_brain_clicked(self) -> None:
        if self._log_window is None:
            self._log_window = ThalamusLogWindow(self, session_id=self._session_id)
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    @Slot(str)
    def _on_log_line(self, text: str) -> None:
        if self._log_window is not None:
            self._log_window.append_line(text)

    # --- chat actions ---

    @Slot()
    def _on_send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.chat.add_turn("human", text)
        self.input.clear()
        self._controller.submit_message(text)

    @Slot(str)
    def _on_reply(self, text: str):
        # successful reply implies "ready"
        self._thalamus_active = True
        self._update_brain_graphic()
        self.chat.add_turn("you", text)

    @Slot(str)
    def _on_error(self, text: str):
        # surface errors immediately during bring-up
        self._thalamus_active = False
        self._update_brain_graphic()
        self.chat.add_turn("system", text)

    @Slot(str, str, str)
    def _on_history_turn(self, role: str, content: str, ts: str):
        # Mark as historical (visible + easy to distinguish)
        self.chat.add_turn(role, content, meta=f"history • {ts}")

    @Slot(bool)
    def _on_busy(self, busy: bool):
        self.send_btn.setDisabled(busy)
        self._llm_active = bool(busy)
        if busy:
            # busy implies connected/active
            self._thalamus_active = True
        self._update_brain_graphic()

    @Slot()
    def _on_config(self):
        dlg = ConfigDialog(self._cfg, self)
        if dlg.exec():
            self._controller.reload_config()
