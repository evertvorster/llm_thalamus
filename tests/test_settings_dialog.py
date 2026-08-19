"""Tests for src/ui/settings_dialog.py — SettingsDialog + Tool Extensions tab.

Requires QT_QPA_PLATFORM=offscreen (set in pytest.ini).
Tests verify dialog construction, widget defaults, and config persistence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt as _Qt

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
    SAMPLE_MODELS = [
        {"id": "deepseek-v4-flash", "provider": "deepseek",
         "name": "DeepSeek V4 Flash", "contextWindow": 1048576},
        {"id": "deepseek-v4-pro", "provider": "deepseek",
         "name": "DeepSeek V4 Pro", "contextWindow": 1048576},
        {"id": "qwythos-abliterated", "provider": "llama-cpp",
         "name": "Huihui Qwythos 9B Abliterated Q6_K", "contextWindow": 316672},
        {"id": "test-model", "provider": "test",
         "name": "Test Model", "contextWindow": 4096},
    ]

    cfg = {
        "theme": "light",
        "defaultProvider": "llama-cpp",
        "defaultModel": "bartowski/google_gemma-4-E2B-it-GGUF:BF16",
        "enabledModels": ["deepseek-v4-flash", "qwythos-abliterated"],
    }
    cfg_path = pi_dir / "settings.json"
    cfg_path.write_text(json.dumps(cfg))

    monkeypatch.setattr(Path, "home", lambda: tmp)
    return cfg_path, cfg, SAMPLE_MODELS


@pytest.fixture
def dialog(monkeypatch, chat_renderer, pi_settings):
    """Create a SettingsDialog that reads from temp pi settings.

    QSettings is isolated to a throwaway ini file so per-test
    persistence (e.g. pricing/models) doesn't leak into other tests.
    """
    from PySide6.QtCore import QSettings as _QtQSettings
    from ui.settings_dialog import SettingsDialog

    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: "/tmp")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **kw: ("/tmp/test.wav", "")
    )

    # Force the module's QSettings to a fresh temp ini per test.
    _ini = tempfile.NamedTemporaryFile(
        suffix=".ini", prefix="llmth-", delete=False
    ).name

    class _IsolatedSettings(_QtQSettings):
        def __init__(self, *a, **kw):
            super().__init__(_ini, _QtQSettings.Format.IniFormat)

    monkeypatch.setattr("ui.settings_dialog.QSettings", _IsolatedSettings)

    _cfg_path, _cfg, sample_models = pi_settings
    dlg = SettingsDialog(
        chat=chat_renderer,
        available_models=sample_models,
        bridge_config_dir="",
        stt_backend=None,
    )
    yield dlg
    dlg.close()
    try:
        Path(_ini).unlink()
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════
#  Dialog creation
# ═══════════════════════════════════════════════════════════════════


class TestDialogCreation:
    """Verify SettingsDialog initializes without errors."""

    def test_creates(self, dialog):
        """Dialog should construct without crashing."""
        assert dialog is not None
        assert dialog.windowTitle() == "Settings"

    def test_has_five_tabs(self, dialog):
        """Should have exactly 5 tabs: Display, pi Backend, STT, Tool Extensions, Pricing."""
        assert dialog._tabs.count() == 5
        labels = [
            dialog._tabs.tabText(i) for i in range(dialog._tabs.count())
        ]
        assert labels == [
            "Display", "pi Backend", "Speech-to-Text",
            "Tool Extensions", "Pricing",
        ]
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
        pi_path, _, _ = pi_settings

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
        pi_path, _, _ = pi_settings
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
        pi_path, _, _ = pi_settings
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


# ═══════════════════════════════════════════════════════════════════
#  Enabled Models — tree widget on pi Backend tab
# ═══════════════════════════════════════════════════════════════════


class TestEnabledModels:
    """Verify the Enabled Models group box on the pi Backend tab."""

    def test_enabled_models_group_exists(self, dialog):
        """The Enabled Models QGroupBox should exist."""
        assert hasattr(dialog, "_models_tree")
        assert dialog._models_tree is not None

    def test_all_models_in_tree(self, dialog):
        """All available models should appear in the tree."""
        total = 0
        for i in range(dialog._models_tree.topLevelItemCount()):
            total += dialog._models_tree.topLevelItem(i).childCount()
        assert total == 4

    def test_initial_check_state_from_settings(self, dialog):
        """Models in enabledModels should be initially checked."""
        from PySide6.QtCore import Qt as _Qt
        checked = set()
        for i in range(dialog._models_tree.topLevelItemCount()):
            prov = dialog._models_tree.topLevelItem(i)
            for j in range(prov.childCount()):
                child = prov.child(j)
                data = child.data(0, _Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict) or data.get("kind") != "model":
                    continue
                if child.checkState(0) == _Qt.CheckState.Checked:
                    checked.add(data["id"])
        assert checked == {"deepseek-v4-flash", "qwythos-abliterated"}

    def test_apply_writes_enabled_models(self, dialog, pi_settings):
        """_apply() should write checked models to settings.json."""
        from PySide6.QtCore import Qt as _Qt
        pi_path, _, _ = pi_settings

        for i in range(dialog._models_tree.topLevelItemCount()):
            prov = dialog._models_tree.topLevelItem(i)
            for j in range(prov.childCount()):
                child = prov.child(j)
                data = child.data(0, _Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict) or data.get("kind") != "model":
                    continue
                if data["id"] == "deepseek-v4-pro":
                    child.setCheckState(0, _Qt.CheckState.Checked)
                if data["id"] == "deepseek-v4-flash":
                    child.setCheckState(0, _Qt.CheckState.Unchecked)

        dialog._apply()

        saved = json.loads(pi_path.read_text())
        enabled = saved.get("enabledModels", [])
        assert "deepseek-v4-pro" in enabled
        assert "deepseek-v4-flash" not in enabled
        assert "qwythos-abliterated" in enabled

    def test_apply_removes_all_when_none_checked(self, dialog, pi_settings):
        """Empty enabledModels when nothing checked."""
        from PySide6.QtCore import Qt as _Qt
        pi_path, _, _ = pi_settings

        for i in range(dialog._models_tree.topLevelItemCount()):
            prov = dialog._models_tree.topLevelItem(i)
            for j in range(prov.childCount()):
                child = prov.child(j)
                data = child.data(0, _Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict) or data.get("kind") != "model":
                    continue
                child.setCheckState(0, _Qt.CheckState.Unchecked)

        dialog._apply()
        saved = json.loads(pi_path.read_text())
        assert saved.get("enabledModels") == []

    def test_provider_groups_exist(self, dialog):
        """Models should be grouped by provider headers."""
        providers = set()
        for i in range(dialog._models_tree.topLevelItemCount()):
            prov = dialog._models_tree.topLevelItem(i)
            providers.add(prov.text(0))
        assert "deepseek" in providers
        assert "llama-cpp" in providers
        assert "test" in providers


# ═══════════════════════════════════════════════════════════════════
#  Pricing tab
# ═══════════════════════════════════════════════════════════════════


class TestPricingTab:
    def _models_item(self, dialog, model_id):
        for i in range(dialog._pricing_models_list.count()):
            it = dialog._pricing_models_list.item(i)
            if it.data(_Qt.ItemDataRole.UserRole) == model_id:
                return it
        raise AssertionError(f"model {model_id!r} not in list")

    def test_tab_exists(self, dialog):
        """Pricing tab should be present with a schedule tree."""
        assert dialog._tabs.tabText(4) == "Pricing"
        assert dialog._pricing_tree is not None

    def test_starts_empty(self, dialog):
        """No schedules → empty tree and disabled editor."""
        assert dialog._pricing_schedules == []
        assert dialog._pricing_tree.topLevelItemCount() == 0
        assert dialog._pricing_models_list.isEnabled() is False

    def test_add_table_seeds_deepseek_defaults(self, dialog):
        """Adding a table seeds DeepSeek's default peak windows."""
        dialog._on_pricing_add()
        assert len(dialog._pricing_schedules) == 1
        s = dialog._pricing_schedules[0]
        assert [(w.start, w.end) for w in s.windows] == [(1, 4), (6, 10)]
        assert dialog._pricing_windows_edit.text() == "01-04, 06-10"
        assert dialog._pricing_tree.topLevelItemCount() == 1
        assert dialog._pricing_models_list.isEnabled() is True

    def test_checking_model_assigns_to_schedule(self, dialog):
        """Checking a model adds it to the selected schedule."""
        dialog._on_pricing_add()
        item = self._models_item(dialog, "deepseek-v4-pro")
        item.setCheckState(_Qt.CheckState.Checked)
        assert "deepseek-v4-pro" in dialog._pricing_schedules[0].models
        # tree label reflects the model name
        assert "DeepSeek V4 Pro" in dialog._pricing_tree.topLevelItem(0).text(0)

    def test_unchecking_model_removes(self, dialog):
        """Unchecking a model removes it from the schedule."""
        dialog._on_pricing_add()
        item = self._models_item(dialog, "test-model")
        item.setCheckState(_Qt.CheckState.Checked)
        item.setCheckState(_Qt.CheckState.Unchecked)
        assert "test-model" not in dialog._pricing_schedules[0].models

    def test_model_only_in_one_table(self, dialog):
        """Checking a model in table B moves it out of table A."""
        dialog._on_pricing_add()          # table 0
        dialog._on_pricing_add()          # table 1 (now selected)
        item = self._models_item(dialog, "deepseek-v4-pro")
        item.setCheckState(_Qt.CheckState.Checked)   # in table 1
        # switch to table 0 and check the same model
        dialog._pricing_tree.setCurrentItem(
            dialog._pricing_tree.topLevelItem(0)
        )
        dialog._on_pricing_selection()
        item2 = self._models_item(dialog, "deepseek-v4-pro")
        item2.setCheckState(_Qt.CheckState.Checked)
        assert "deepseek-v4-pro" in dialog._pricing_schedules[0].models
        assert "deepseek-v4-pro" not in dialog._pricing_schedules[1].models

    def test_windows_edit_valid(self, dialog):
        """Editing the window text updates the schedule."""
        dialog._on_pricing_add()
        dialog._pricing_windows_edit.setText("06-10, 01-04")
        dialog._on_pricing_windows_edited()
        s = dialog._pricing_schedules[0]
        assert [(w.start, w.end) for w in s.windows] == [(6, 10), (1, 4)]

    def test_windows_edit_invalid_keeps_value(self, dialog, monkeypatch):
        """Bad input warns and leaves the schedule unchanged."""
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: None)
        dialog._on_pricing_add()
        original = [(w.start, w.end) for w in dialog._pricing_schedules[0].windows]
        dialog._pricing_windows_edit.setText("nonsense")
        dialog._on_pricing_windows_edited()
        assert [(w.start, w.end) for w in dialog._pricing_schedules[0].windows] == original
        # field reverted to the previous valid value
        assert dialog._pricing_windows_edit.text() == "01-04, 06-10"

    def test_apply_saves_schedules(self, dialog):
        """_apply persists schedules to QSettings."""
        from controller.peak_pricing import load_schedules
        dialog._on_pricing_add()
        dialog._pricing_schedules[0].models.append("test-model")
        dialog._apply()
        saved = load_schedules(dialog._settings)
        assert any("test-model" in s.models for s in saved)
