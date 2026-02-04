from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextEdit, QHBoxLayout
)
from PySide6.QtCore import Slot

from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog


class MainWindow(QWidget):
    def __init__(self, cfg, controller):
        super().__init__()
        self.setWindowTitle("llm_thalamus")

        self._cfg = cfg
        self._controller = controller

        self.chat = ChatRenderer()
        self.input = QTextEdit()
        self.input.setFixedHeight(80)

        self.send_btn = QPushButton("Send")
        self.config_btn = QPushButton("Config")

        btns = QHBoxLayout()
        btns.addWidget(self.send_btn)
        btns.addWidget(self.config_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.chat)
        layout.addWidget(self.input)
        layout.addLayout(btns)

        # wiring
        self.send_btn.clicked.connect(self._on_send)
        self.config_btn.clicked.connect(self._on_config)

        controller.assistant_message.connect(self._on_reply)
        controller.busy_changed.connect(self._on_busy)
        controller.error.connect(self._on_error)

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
        self.chat.add_turn("you", text)

    @Slot(str)
    def _on_error(self, text: str):
        self.chat.add_turn("system", text)

    @Slot(bool)
    def _on_busy(self, busy: bool):
        self.send_btn.setDisabled(busy)

    @Slot()
    def _on_config(self):
        dlg = ConfigDialog(self._cfg, self)
        if dlg.exec():
            self._controller.reload_config()
