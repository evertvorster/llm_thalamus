"""llm-thalamus — Qt desktop GUI for the pi coding agent (RPC backend)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer

from controller.pi_bridge import PiRPCBridge
from ui.chat_renderer import ChatRenderer
from ui.widgets import BrainWidget, ChatInput


# ── path resolution ──────────────────────────────────────────────────


def _resolve_paths(dev_mode: bool) -> tuple[Path, Path]:
    """Return (pi_config_dir, graphics_dir) based on dev/installed mode."""
    if dev_mode:
        # Repo root is parent of the src/ directory containing this file.
        repo_root = Path(__file__).resolve().parent.parent
        pi_config = repo_root / "resources" / "pi-config"
        graphics = repo_root / "resources" / "graphics"
    else:
        pi_config = Path("/usr/share/llm-thalamus/pi-config")
        graphics = Path("/usr/share/llm-thalamus/graphics")
    return pi_config, graphics


# ── minimal main window ──────────────────────────────────────────────


class MainWindow(QWidget):
    """A minimal Qt window connecting PiRPCBridge signals to ChatRenderer."""

    def __init__(self, bridge: PiRPCBridge, graphics_dir: Path):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._bridge = bridge
        self._streaming: bool = False

        # --- left: chat renderer + input area ---
        self.chat = ChatRenderer()

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send)

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

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(splitter, 1)

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

    # ── slot: send ───────────────────────────────────────────────

    def _on_send(self) -> None:
        if not self.send_button.isEnabled():
            return
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat.add_turn("human", text)
        self.chat_input.clear()
        self._bridge.submit_message(text)

    # ── slots: streaming ─────────────────────────────────────────

    def _on_stream_start(self) -> None:
        self._streaming = True
        self.chat.begin_assistant_stream()

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

    def _on_thinking_delta(self, _text: str) -> None:
        pass  # brain animation handles thinking visually

    def _on_thinking_finished(self) -> None:
        self.brain.set_saturation(1.0)

    # ── slots: tools ─────────────────────────────────────────────

    def _on_tool_start(self, call_id: str, name: str, _args: dict) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_call",
            "payload": {"tool_call_id": call_id, "tool_name": name},
        })

    def _on_tool_end(self, call_id: str, name: str, result_text: str, is_error: bool) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_result",
            "payload": {"tool_name": name, "result": result_text, "is_error": is_error},
        })

    # ── slots: lifecycle ─────────────────────────────────────────

    def _on_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.brain.set_state("llm" if busy else "thalamus")

    def _on_error(self, text: str) -> None:
        self.chat.add_turn("system", text)
        self.brain.set_state("inactive")

    def _on_history_turn(self, role: str, content: str, _ts: str) -> None:
        # Map pi roles to chat renderer roles.
        # pi roles: "user", "assistant", "toolResult", "bashExecution"
        display_role = "human" if role == "user" else "you"
        self.chat.add_turn(display_role, content)


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    dev_mode = "--dev" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("llm-thalamus")

    pi_config, graphics = _resolve_paths(dev_mode)

    bridge = PiRPCBridge(pi_config_dir=str(pi_config))
    window = MainWindow(bridge, graphics)

    # Start pi and load history once the event loop is running.
    QTimer.singleShot(0, lambda: _on_startup(bridge, window))

    window.show()
    sys.exit(app.exec())


def _on_startup(bridge: PiRPCBridge, window: MainWindow) -> None:
    bridge.start()
    bridge.load_history()


if __name__ == "__main__":
    main()
