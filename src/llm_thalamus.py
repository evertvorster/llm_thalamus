"""llm-thalamus — Qt desktop GUI for the pi coding agent (RPC backend)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from controller.pi_bridge import PiRPCBridge
from ui.main_window import MainWindow


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
    # Select Gemma 4 E2B as the default model.
    bridge.send_command({
        "type": "set_model",
        "provider": "llama-cpp",
        "modelId": "bartowski/google_gemma-4-E2B-it-GGUF:BF16",
    })
    bridge.load_history()


if __name__ == "__main__":
    main()
