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
    QFrame,
    QLabel,
    QSizePolicy,
)
from PySide6.QtCore import Slot, Qt, QTimer

from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog
from ui.widgets import (
    BrainWidget,
    ThalamusLogWindow,
    ChatInput,
    ThoughtLogWindow,
    WorldSummaryWidget,
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
        self._log_window: ThalamusLogWindow | None = None
        self._thought_window: ThoughtLogWindow | None = None
        self._session_id = str(int(time.time()))

        # --- thinking channel state (ephemeral, per-request) ---
        self._thinking_buffer: list[str] = []
        self._thinking_active: bool = False

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

        # --- right: brain at top + spaces panel below ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.brain_widget = BrainWidget(cfg.graphics_dir)
        self.brain_widget.clicked.connect(self._on_brain_clicked)
        self.brain_widget.setMinimumSize(220, 220)

        self.thinking_button = QPushButton("Thinking")
        self.thinking_button.setEnabled(False)  # enabled when we receive any thinking text
        self.thinking_button.clicked.connect(self._on_thinking_clicked)
        # Make it span the full width of the right panel column
        self.thinking_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # --- thinking pulse animation (UI-only) ---
        self._thinking_pulse_timer = QTimer(self)
        self._thinking_pulse_timer.setInterval(300)
        self._thinking_pulse_timer.timeout.connect(self._on_thinking_pulse_tick)

        self._thinking_pulse_phase: int = 0
        self._thinking_button_base_text: str = self.thinking_button.text()
        self._thinking_button_base_style: str = self.thinking_button.styleSheet()

        # Subtle pulse styles (safe on dark background)
        self._thinking_pulse_style_a = (
            self._thinking_button_base_style
            + "QPushButton { background-color: rgba(255,255,255,18); }"
        )
        self._thinking_pulse_style_b = (
            self._thinking_button_base_style
            + "QPushButton { background-color: rgba(255,255,255,32); }"
        )

        # Replace placeholder with a read-only world summary widget.
        # IMPORTANT: the UI does not resolve config paths; it asks controller for the world path.
        self.spaces_panel = WorldSummaryWidget()
        self.spaces_panel.setMinimumWidth(260)

        right_layout.addWidget(self.thinking_button, 0)
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

        # wiring from controller
        controller.assistant_message.connect(self._on_reply)
        controller.busy_changed.connect(self._on_busy)
        controller.error.connect(self._on_error)
        controller.log_line.connect(self._on_log_line)
        controller.history_turn.connect(self._on_history_turn)

        # thinking channel (optional per-model)
        controller.thinking_started.connect(self._on_thinking_started)
        controller.thinking_delta.connect(self._on_thinking_delta)
        controller.thinking_finished.connect(self._on_thinking_finished)

        # world committed (reflect/store completed)
        if hasattr(controller, "world_committed"):
            controller.world_committed.connect(self._on_world_committed)

        # initial brain state
        self._update_brain_graphic()

        # load history once on startup
        controller.emit_history()

        # initial world summary paint (best-effort)
        self._refresh_world_summary()

        # Seed the vertical splitter *after* first layout so geometry is correct
        QTimer.singleShot(0, self._seed_chat_splitter)

    # --- splitter seeding ---

    def _seed_chat_splitter(self) -> None:
        # Give chat most space, but keep input comfortably large.
        h = max(self.height(), 700)
        input_h = int(h * 0.20)   # ~28% input area
        chat_h = max(h - input_h, 200)
        self._chat_splitter.setSizes([chat_h, input_h])

    def closeEvent(self, event) -> None:
        # Ensure controller thread is stopped before the UI exits.
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
            # Spaces panel must never break UI responsiveness.
            return

    @Slot()
    def _on_world_committed(self) -> None:
        self._refresh_world_summary()

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

        # Toggle: click again to close/hide if it's already open
        if self._log_window.isVisible():
            self._log_window.hide()
        else:
            self._log_window.show()
            self._log_window.raise_()
            self._log_window.activateWindow()

    @Slot()
    def _on_thinking_clicked(self) -> None:
        if self._thought_window is None:
            self._thought_window = ThoughtLogWindow(self, session_id=self._session_id)

        # Toggle window on repeated clicks (same UX as brain log)
        if self._thought_window.isVisible():
            self._thought_window.hide()
        else:
            self._thought_window.show()
            self._thought_window.raise_()
            self._thought_window.activateWindow()

    @Slot(str)
    def _on_log_line(self, text: str) -> None:
        if self._log_window is not None:
            self._log_window.append_line(text)

    # --- thinking channel (signals) ---

    @Slot()
    def _on_thinking_started(self) -> None:
        self._thinking_active = True
        self._thinking_buffer = []
        self.thinking_button.setEnabled(False)  # enabled on first delta
        self._start_thinking_pulse()

    @Slot(str)
    def _on_thinking_delta(self, text: str) -> None:
        if not text:
            return

        self._thinking_buffer.append(text)

        # Enable button as soon as we have any thinking content.
        if not self.thinking_button.isEnabled():
            self.thinking_button.setEnabled(True)

        # If the thought window is open, append live.
        if self._thought_window is not None and self._thought_window.isVisible():
            self._thought_window.append_text(text)

    @Slot()
    def _on_thinking_finished(self) -> None:
        self._thinking_active = False
        self._stop_thinking_pulse()

        # Keep enabled iff we collected any thinking text.
        self.thinking_button.setEnabled(bool(self._thinking_buffer))

        # If the window is open, ensure it contains the full buffer
        # (in case the user opened it late).
        if self._thought_window is not None and self._thought_window.isVisible():
            self._thought_window.clear()
            self._thought_window.append_text("".join(self._thinking_buffer))

    # --- send / input ---

    @Slot()
    def _on_send_clicked(self) -> None:
        if not self.send_button.isEnabled():
            return

        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        # Per-request thinking is ephemeral; reset UI state on send.
        self._thinking_buffer = []
        self._thinking_active = False
        self._stop_thinking_pulse()
        self.thinking_button.setEnabled(False)

        # If the thought window is open, clear it for the new request.
        if self._thought_window is not None:
            self._thought_window.clear()

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

    # --- thinking pulse helpers (UI-only) ---

    def _start_thinking_pulse(self) -> None:
        self._thinking_pulse_phase = 0
        self.thinking_button.setText("Thinking")
        self.thinking_button.setStyleSheet(self._thinking_pulse_style_a)
        if self._thinking_pulse_timer is not None and not self._thinking_pulse_timer.isActive():
            self._thinking_pulse_timer.start()

    def _stop_thinking_pulse(self) -> None:
        # Be defensive in case this is called during teardown.
        if hasattr(self, "_thinking_pulse_timer") and self._thinking_pulse_timer.isActive():
            self._thinking_pulse_timer.stop()

        if hasattr(self, "thinking_button"):
            self.thinking_button.setText(getattr(self, "_thinking_button_base_text", "Thinking"))
            self.thinking_button.setStyleSheet(getattr(self, "_thinking_button_base_style", ""))

    @Slot()
    def _on_thinking_pulse_tick(self) -> None:
        if not self._thinking_active:
            self._stop_thinking_pulse()
            return

        self._thinking_pulse_phase += 1

        # Alternate background for pulse
        if self._thinking_pulse_phase % 2 == 0:
            self.thinking_button.setStyleSheet(self._thinking_pulse_style_a)
        else:
            self.thinking_button.setStyleSheet(self._thinking_pulse_style_b)

        # Animate dots: Thinking → Thinking.
        dots = self._thinking_pulse_phase % 4
        self.thinking_button.setText("Thinking" + "." * dots)
