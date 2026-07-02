"""llm-thalamus — Qt desktop GUI for the pi coding agent (RPC backend)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
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


# ── session discovery ──────────────────────────────────────────────


def _find_latest_session_cwd(pi_config_dir: str) -> str | None:
    """Find the most recently modified session across all CWD directories.

    Scans ``~/.pi/agent/sessions/*/`` (or ``{pi_config_dir}/sessions/*/`` when
    *pi_config_dir* is set) for the ``.jsonl`` file with the newest mtime.
    Returns the ``cwd`` from its JSONL header, or ``None`` if no session
    exists or the CWD is unavailable.
    """
    if pi_config_dir:
        sessions_root = Path(pi_config_dir) / "sessions"
    else:
        sessions_root = Path.home() / ".pi" / "agent" / "sessions"

    if not sessions_root.is_dir():
        return None

    latest: str | None = None
    latest_mtime: float = 0

    for entry in sessions_root.iterdir():
        if not entry.is_dir() or entry.name == "attachments" or entry.name.startswith("."):
            continue
        for f in entry.iterdir():
            if f.suffix == ".jsonl":
                mtime = f.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest = str(f)

    if not latest:
        return None

    # Read the cwd from the session file header (first JSON line).
    try:
        with open(latest, "r", encoding="utf-8") as f:
            first = f.readline()
        if not first:
            return None
        header = json.loads(first)
        cwd = header.get("cwd")
        return str(cwd) if cwd else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


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
    icon_path = graphics / "llm_thalamus.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    pi_config_dir = _load_pi_config_dir()

    bridge = PiRPCBridge(pi_config_dir=pi_config_dir)
    window = MainWindow(bridge, graphics)

    # Start pi and load history once the event loop is running.
    QTimer.singleShot(0, lambda: _on_startup(bridge))

    window.show()
    sys.exit(app.exec())


def _on_startup(bridge: PiRPCBridge) -> None:
    cwd = _find_latest_session_cwd(bridge._pi_config_dir)
    if cwd and Path(cwd).is_dir():
        os.chdir(cwd)
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
