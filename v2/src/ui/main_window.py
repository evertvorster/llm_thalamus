from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import Slot, Qt, QTimer, QSequentialAnimationGroup, QPropertyAnimation, QEasingCurve, QAbstractAnimation

from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog
from ui.widgets import (
    BrainWidget,
    ChatInput,
    WorldSummaryWidget,
    CombinedLogsWindow,
)


class MainWindow(QWidget):
    def __init__(self, cfg, controller):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._cfg = cfg
        self._controller = controller

        # --- brain/log state ---
        self._thalamus_active = True
        self._llm_active = False
        self._logs_window: CombinedLogsWindow | None = None
        self._session_id = str(int(time.time()))

        # --- thinking channel state (ephemeral, per-request) ---
        self._thinking_buffer: list[str] = []

        # --- left: chat renderer + input area ---
        self.chat = ChatRenderer()

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send_clicked)

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
        input_container.setMinimumHeight(0)

        min_h = (
            self.send_button.sizeHint().height() * 3
            + buttons_col.spacing() * 2
        )
        self.chat_input.setMinimumHeight(min_h)
        self.chat_input.setSizePolicy(
            self.chat_input.sizePolicy().horizontalPolicy(),
            QSizePolicy.Expanding,
        )

        # Splitter between chat history (top) and input area (bottom)
        self._chat_splitter = QSplitter(Qt.Vertical, self)
        self._chat_splitter.addWidget(self.chat)
        self._chat_splitter.addWidget(input_container)
        self._chat_splitter.setStretchFactor(0, 4)
        self._chat_splitter.setStretchFactor(1, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self._chat_splitter, 1)

        # --- right: brain at top + world view panel below ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.brain_widget = BrainWidget(cfg.graphics_dir)
        self.brain_widget.clicked.connect(self._on_brain_clicked)
        self.brain_widget.setMinimumSize(220, 220)

        # Smooth thinking animation: saturate 1.0 <-> 0.7 in a loop
        self._thinking_anim = QSequentialAnimationGroup(self)

        a1 = QPropertyAnimation(self.brain_widget, b"saturation", self)
        a1.setStartValue(1.00)
        a1.setEndValue(0.70)
        a1.setDuration(900)
        a1.setEasingCurve(QEasingCurve.InOutSine)

        a2 = QPropertyAnimation(self.brain_widget, b"saturation", self)
        a2.setStartValue(0.70)
        a2.setEndValue(1.00)
        a2.setDuration(900)
        a2.setEasingCurve(QEasingCurve.InOutSine)

        self._thinking_anim.addAnimation(a1)
        self._thinking_anim.addAnimation(a2)
        self._thinking_anim.setLoopCount(-1)

        # World view widget
        self.spaces_panel = WorldSummaryWidget()
        self.spaces_panel.setMinimumWidth(260)

        right_layout.addWidget(self.brain_widget, 0, Qt.AlignHCenter)
        right_layout.addWidget(self.spaces_panel, 1)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(splitter, 1)

        # wiring from controller (snapshot signal names)
        controller.assistant_message.connect(self._on_reply)
        controller.busy_changed.connect(self._on_busy)
        controller.error.connect(self._on_error)
        controller.log_line.connect(self._on_log_line)
        controller.history_turn.connect(self._on_history_turn)

        controller.thinking_started.connect(self._on_thinking_started)
        controller.thinking_delta.connect(self._on_thinking_delta)
        controller.thinking_finished.connect(self._on_thinking_finished)

        if hasattr(controller, "world_committed"):
            controller.world_committed.connect(self._on_world_committed)

        # initial brain state
        self._update_brain_graphic()
        self.brain_widget.set_saturation(1.0)

        # load history once on startup
        controller.emit_history()

        # initial world summary paint (best-effort)
        self._refresh_world_summary()

        # Seed the vertical splitter after first layout so geometry is correct
        QTimer.singleShot(0, self._seed_chat_splitter)

    # --- splitter seeding ---

    def _seed_chat_splitter(self) -> None:
        h = max(self.height(), 700)
        input_h = int(h * 0.20)
        chat_h = max(h - input_h, 200)
        self._chat_splitter.setSizes([chat_h, input_h])

    def closeEvent(self, event) -> None:
        try:
            if hasattr(self._controller, "shutdown"):
                self._controller.shutdown()
        finally:
            event.accept()

    # --- world summary (Spaces panel) ---

    def _refresh_world_summary(self) -> None:
        """
        Refresh the Spaces panel by reading world_state.json.

        NOTE: do not resolve paths/config here. Delegate to controller.
        """
        try:
            world_path = self._controller._world_state_path
        except Exception:
            return

        try:
            self.spaces_panel.refresh_from_path(Path(world_path))
        except Exception:
            return

    @Slot()
    def _on_world_committed(self) -> None:
        self._refresh_world_summary()

    # --- brain & combined logs window ---

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
        if self._logs_window is None:
            self._logs_window = CombinedLogsWindow(self, session_id=self._session_id)

        if self._logs_window.isVisible():
            self._logs_window.hide()
            return

        self._logs_window.set_thinking_text("".join(self._thinking_buffer))

        self._logs_window.show()
        self._logs_window.raise_()
        self._logs_window.activateWindow()

    @Slot(str)
    def _on_log_line(self, text: str) -> None:
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.append_thalamus_line(text)

    # --- thinking channel (signals) ---

    @Slot()
    def _on_thinking_started(self) -> None:
        self._thinking_buffer = []
        # Start smooth animation
        if self._thinking_anim.state() != QAbstractAnimation.Running:
            self._thinking_anim.start()

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("")

    @Slot(str)
    def _on_thinking_delta(self, text: str) -> None:
        if not text:
            return

        self._thinking_buffer.append(text)

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.append_thinking_text(text)

    @Slot()
    def _on_thinking_finished(self) -> None:
        # Stop animation and restore full saturation
        if self._thinking_anim.state() == QAbstractAnimation.Running:
            self._thinking_anim.stop()
        self.brain_widget.set_saturation(1.0)

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("".join(self._thinking_buffer))

    # --- send / input ---

    @Slot()
    def _on_send_clicked(self) -> None:
        if not self.send_button.isEnabled():
            return

        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        # reset per-request thinking
        self._thinking_buffer = []
        if self._thinking_anim.state() == self._thinking_anim.Running:
            self._thinking_anim.stop()
        self.brain_widget.set_saturation(1.0)

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("")

        self.chat.add_turn("human", text)
        self.chat_input.clear()
        self._controller.submit_message(text)

    @Slot(bool)
    def _on_busy(self, busy: bool) -> None:
        self.send_button.setDisabled(busy)
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
        self._thalamus_active = False
        self._update_brain_graphic()
        self.chat.add_turn("system", text)

    @Slot(str, str, str)
    def _on_history_turn(self, role: str, content: str, ts: str) -> None:
        self.chat.add_turn(role, content, meta=f"history • {ts}")

    # --- config / quit ---

    def _write_config_file(self, new_cfg: dict) -> None:
        path = Path(self._cfg.config_file)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")

    @Slot(dict, bool)
    def _on_config_applied(self, new_cfg: dict, _should_restart: bool) -> None:
        self._write_config_file(new_cfg)
        self._controller.reload_config()

    @Slot()
    def _on_config_clicked(self) -> None:
        dlg = ConfigDialog(self._cfg.raw, self)
        dlg.configApplied.connect(self._on_config_applied)
        dlg.exec()

    @Slot()
    def _on_quit_clicked(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
