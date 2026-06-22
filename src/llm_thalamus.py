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
    """Return the custom pi config dir based on dev/installed mode.

    Only used when --local is passed on the command line.
    """
    if dev_mode:
        return Path(__file__).resolve().parent.parent / "resources" / "pi-config"
    return Path("/usr/share/llm-thalamus/pi-config")


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    dev_mode = "--dev" in sys.argv
    local_mode = "--local" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("llm-thalamus")

    graphics = _resolve_graphics_dir(dev_mode)

    if local_mode:
        pi_config_dir = str(_resolve_pi_config_dir(dev_mode))
    else:
        pi_config_dir = ""  # use pi's default config at ~/.pi/agent/

    bridge = PiRPCBridge(pi_config_dir=pi_config_dir)
    window = MainWindow(bridge, graphics)

    # Start pi and load history once the event loop is running.
    QTimer.singleShot(0, lambda: _on_startup(bridge, local_mode=local_mode))

    window.show()
    sys.exit(app.exec())


def _on_startup(bridge: PiRPCBridge, *, local_mode: bool) -> None:
    bridge.start(resume=True)
    if local_mode:
        # When using the local-only pi config, explicitly select
        # a model from the llama-cpp provider.
        bridge.send_command({
            "type": "set_model",
            "provider": "llama-cpp",
            "modelId": "bartowski/google_gemma-4-E2B-it-GGUF:BF16",
        })
    # When using the default pi config, pi already knows what model
    # the user has selected — don't override it.
    bridge.load_history()


if __name__ == "__main__":
    main()
