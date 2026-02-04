from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QFrame,
    QLabel,
)
from PySide6.QtCore import Slot, Qt

from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog
from ui.widgets import BrainWidget, ThalamusLogWindow, ChatInput


class MainWindow(QWidget):
    def __init__(self, cfg, controller):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        # Match the old default window size
        self.resize(1100, 700)

        self._cfg = cfg
        self._controller = controller

        # --- brain/log state ---
        self._thalamus_active = True
        self._llm_active = False
        self._log_window: ThalamusLogWindow | None = None
        self._session_id = str(int(time.time()))

        # --- left: chat renderer + input area ---
        self.chat = ChatRenderer()

        # Input widget with Enter-to-send behavior
        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send_clicked)

        # Buttons column (Send / Config / Quit) in vertical arrangement
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)

        self.config_button = QPushButton("Config")
        self.config_button.clicked.connect(self._on_config_clicked)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self._on_quit_clicked)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(4, 0, 0, 0)
        buttons_col.setSpacing(4)
        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.config_button)
        buttons_col.addWidget(self.quit_button)
        buttons_col.addStretch(1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)
        input_row.addLayout(buttons_col, 0)

        input_container = QWidget()
        input_container.setLayout(input_row)
        input_container.setMinimumHeight(120)

        # Splitter between chat history (top) and input area (bottom)
        chat_splitter = QSplitter(Qt.Vertical, self)
        chat_splitter.addWidget(self.chat)
        chat_splitter.addWidget(input_container)
        chat_splitter.setStretchFactor(0, 4)
        chat_splitter.setStretchFactor(1, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(chat_splitter, 1)

        # --- right: brain at top right + spaces placeholder below ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.brain_widget = BrainWidget(cfg.graphics_dir)
        self.brain_widget.clicked.connect(self._on_brain_clicked)
        self.brain_widget.setMinimumSize(220, 220)

        # Blank panel for spaces (disabled)
        self.spaces_panel = QFrame()
        self.spaces_panel.setFrameShape(QFrame.StyledPanel)
        self.spaces_panel.setMinimumWidth(260)

        spaces_layout = QVBoxLayout(self.spaces_panel)
        spaces_layout.setContentsMargins(10, 10, 10, 10)
        spaces_layout.setSpacing(6)
        spaces_layout.addWidget(QLabel("Spaces (disabled for now)"), 0, Qt.AlignTop)
        spaces_layout.addStretch(1)

        right_layout.addWidget(self.brain_widget, 0, Qt.AlignHCenter)

        right_layout.addWidget(self.spaces_panel, 1)

        # --- main splitter: chat (left) + right panel ---
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(splitter, 1)

        # wiring from controller
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

    # --- send / input ---

    @Slot()
    def _on_send_clicked(self) -> None:
        # Enforce the same busy gating as the Send button:
        if not self.send_button.isEnabled():
            return

        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        self.chat.add_turn("human", text)
        self.chat_input.clear()

        self._controller.submit_message(text)

    @Slot(bool)
    def _on_busy(self, busy: bool) -> None:
        self.send_button.setDisabled(busy)
        # Keep typing allowed; but Enter-to-send is gated by send button enabled.
        self._llm_active = bool(busy)
        if busy:
            self._thalamus_active = True
        self._update_brain_graphic()

    @Slot(str)
    def _on_reply(self, text: str) -> None:
        self._thalamus_active = True
        self._update_brain_graphic()
        self.chat.add_turn("you", text)

    @Slot(str)
    def _on_error(self, text: str) -> None:
        # during runtime errors, show inactive until next success
        self._thalamus_active = False
        self._update_brain_graphic()
        self.chat.add_turn("system", text)

    @Slot(str, str, str)
    def _on_history_turn(self, role: str, content: str, ts: str) -> None:
        self.chat.add_turn(role, content, meta=f"history • {ts}")

    # --- config / quit ---

    @Slot()
    def _on_config_clicked(self) -> None:
        dlg = ConfigDialog(self._cfg, self)
        if dlg.exec():
            self._controller.reload_config()

    @Slot()
    def _on_quit_clicked(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
