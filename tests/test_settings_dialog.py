"""Tests for src/ui/settings_dialog.py — SettingsDialog + Tool Extensions tab.

Requires QT_QPA_PLATFORM=offscreen (set in pytest.ini).
Tests verify dialog construction, widget defaults, and config persistence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session (offscreen)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def chat_renderer(qapp):
    """Create a ChatRenderer instance for SettingsDialog construction."""
    from ui.chat_renderer import ChatRenderer
    return ChatRenderer()


@pytest.fixture
def pi_settings(monkeypatch):
    """Create a temp home dir with settings.json, monkeypatch Path.home()."""
    tmp = Path(tempfile.mkdtemp())
    pi_dir = tmp / ".pi" / "agent"
    pi_dir.mkdir(parents=True)
    cfg = {
        "theme": "light",
        "defaultProvider": "llama-cpp",
        "defaultModel": "bartowski/google_gemma-4-E2B-it-GGUF:BF16",
    }
    cfg_path = pi_dir / "settings.json"
    cfg_path.write_text(json.dumps(cfg))

    monkeypatch.setattr(Path, "home", lambda: tmp)
    return cfg_path, cfg


@pytest.fixture
def dialog(monkeypatch, chat_renderer, pi_settings):
    """Create a SettingsDialog that reads from temp pi settings."""
    from ui.settings_dialog import SettingsDialog

    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: "/tmp")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **kw: ("/tmp/test.wav", "")
    )

    dlg = SettingsDialog(
        chat=chat_renderer,
        available_models=[{"id": "test-model", "provider": "test"}],
        bridge_config_dir="",
        stt_backend=None,
    )
    yield dlg
    dlg.close()


# ═══════════════════════════════════════════════════════════════════
#  Dialog creation
# ═══════════════════════════════════════════════════════════════════


class TestDialogCreation:
    """Verify SettingsDialog initializes without errors."""

    def test_creates(self, dialog):
        """Dialog should construct without crashing."""
        assert dialog is not None
        assert dialog.windowTitle() == "Settings"

    def test_has_four_tabs(self, dialog):
        """Should have exactly 4 tabs: Display, pi Backend, STT, Tool Extensions."""
        assert dialog._tabs.count() == 4
        assert dialog._tabs.tabText(0) == "Display"
        assert dialog._tabs.tabText(1) == "pi Backend"
        assert dialog._tabs.tabText(2) == "Speech-to-Text"
        assert dialog._tabs.tabText(3) == "Tool Extensions"


# ═══════════════════════════════════════════════════════════════════
#  Tool Extensions tab — widget defaults
# ═══════════════════════════════════════════════════════════════════


class TestToolExtensionsDefaults:
    """Verify Tool Extensions tab widgets are created with correct defaults."""

    def test_path_widgets_exist(self, dialog):
        """All path widgets should exist with correct defaults."""
        assert dialog._sdxl_model.text() == "/home/evert/models/sdxl-base"
        assert dialog._sd15_model.text() == "/home/evert/models/sd15"
        assert "Pictures/Stable Diffusion" in dialog._img_out.text()
        assert "Voice_Sample2.wav" in dialog._voice_sample.text()
        assert dialog._tts_out.text() == "/tmp"

    def test_tts_model_combo_populated(self, dialog):
        """TTS model dropdown should be populated with model URIs."""
        assert dialog._tts_direct_model.count() > 0
        assert dialog._tts_direct_model.currentText() == \
            "tts_models/en/ljspeech/tacotron2-DDC"
        items = [dialog._tts_direct_model.itemText(i)
                 for i in range(dialog._tts_direct_model.count())]
        assert "tts_models/multilingual/multi-dataset/xtts_v2" in items
        assert "tts_models/en/jenny/jenny" in items
        assert "tts_models/de/thorsten/tacotron2-DDC" in items

    def test_tts_models_list_length(self, dialog):
        """TTS model list should have 21 entries."""
        assert dialog._tts_direct_model.count() == 21


# ═══════════════════════════════════════════════════════════════════
#  Tool Extensions tab — config persistence
# ═══════════════════════════════════════════════════════════════════


class TestToolExtensionsPersistence:
    """Verify _apply() writes extension config keys to settings.json."""

    def test_apply_saves_extension_keys(self, dialog, pi_settings):
        """All extension config keys should be written on _apply()."""
        pi_path, _ = pi_settings

        dialog._sdxl_model.setText("/custom/sdxl")
        dialog._sd15_model.setText("/custom/sd15")
        dialog._img_out.setText("/custom/images")
        dialog._voice_sample.setText("/custom/sample.wav")
        dialog._tts_out.setText("/custom/tts")
        dialog._tts_direct_model.setCurrentText(
            "tts_models/en/ljspeech/glow-tts"
        )

        dialog._apply()

        saved = json.loads(pi_path.read_text())
        assert saved["sdxl_model_path"] == "/custom/sdxl"
        assert saved["sd15_model_path"] == "/custom/sd15"
        assert saved["image_output_dir"] == "/custom/images"
        assert saved["voice_sample_path"] == "/custom/sample.wav"
        assert saved["tts_output_dir"] == "/custom/tts"
        assert saved["tts_direct_model"] == "tts_models/en/ljspeech/glow-tts"

    def test_apply_saves_both_old_and_new_keys(self, dialog, pi_settings):
        """Extension keys are added alongside existing settings keys."""
        pi_path, _ = pi_settings
        dialog._apply()
        saved = json.loads(pi_path.read_text())
        # Original keys still present
        assert "defaultProvider" in saved
        assert "defaultModel" in saved
        # Extension keys added
        assert saved.get("sdxl_model_path") == "/home/evert/models/sdxl-base"
        assert saved.get("tts_output_dir") == "/tmp"

    def test_apply_overwrites_changed(self, dialog, pi_settings):
        """Changing a value and applying should overwrite old value."""
        pi_path, _ = pi_settings
        old = json.loads(pi_path.read_text())
        assert "tts_output_dir" not in old

        dialog._tts_out.setText("/custom/tts-dir")
        dialog._apply()
        saved = json.loads(pi_path.read_text())
        assert saved["tts_output_dir"] == "/custom/tts-dir"


# ═══════════════════════════════════════════════════════════════════
#  STT tab — early return path (no backend)
# ═══════════════════════════════════════════════════════════════════


class TestSttTabWithoutBackend:
    """STT tab should handle absent backend gracefully."""

    def test_stt_tab_exists(self, dialog):
        """STT tab widget exists when backend is None."""
        tab = dialog._tabs.widget(2)
        assert tab is not None
        # Tab exists — _build_stt_tab took the early-return path
        # and added its stretch + tab normally
        assert dialog._tabs.tabText(2) == "Speech-to-Text"
