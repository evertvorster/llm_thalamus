"""llm-thalamus — Qt desktop GUI for the pi coding agent (RPC backend)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from controller.pi_bridge import PiRPCBridge
from ui.main_window import MainWindow


# ── path resolution ──────────────────────────────────────────────────


def _resolve_graphics_dir(dev_mode: bool) -> Path:
    """Return the graphics directory based on dev/installed mode."""
    if dev_mode:
        return Path(__file__).resolve().parent.parent / "resources" / "graphics"
    return Path("/usr/share/llm-thalamus/graphics")


def _resolve_pi_config_dir(dev_mode: bool) -> Path:
    """Return the shipped local pi config dir based on dev/installed mode."""
    if dev_mode:
        return Path(__file__).resolve().parent.parent / "resources" / "pi-config"
    return Path("/usr/share/llm-thalamus/pi-config")


# ── main ─────────────────────────────────────────────────────────────


def _load_pi_config_dir() -> str:
    """Return the pi config directory from QSettings.

    Controlled by the settings dialog (pi Backend → pi Config section).
    Returns ``""`` (empty) for the default pi config at ``~/.pi/agent/``.
    """
    from PySide6.QtCore import QSettings
    s = QSettings("llm-thalamus", "llm-thalamus")
    saved = s.value("pi/config_dir", "")
    if saved and isinstance(saved, str) and saved.strip():
        return saved.strip()
    return ""


def main() -> None:
    dev_mode = "--dev" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("llm-thalamus")

    graphics = _resolve_graphics_dir(dev_mode)
    pi_config_dir = _load_pi_config_dir()

    bridge = PiRPCBridge(pi_config_dir=pi_config_dir)
    window = MainWindow(bridge, graphics)

    # Start pi and load history once the event loop is running.
    QTimer.singleShot(0, lambda: _on_startup(bridge))

    window.show()
    sys.exit(app.exec())


def _on_startup(bridge: PiRPCBridge) -> None:
    bridge.start(resume=True)
    # If using a custom/local pi config, set the default model.
    if bridge._pi_config_dir:
        bridge.send_command({
            "type": "set_model",
            "provider": "llama-cpp",
            "modelId": "bartowski/google_gemma-4-E2B-it-GGUF:BF16",
        })
    bridge.load_history()


if __name__ == "__main__":
    main()
