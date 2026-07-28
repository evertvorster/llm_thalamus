"""Tests for src/ui/model_dialog.py — ModelPickerDialog.

Requires QT_QPA_PLATFORM=offscreen (set in pytest.ini).
"""

from __future__ import annotations

from PySide6.QtCore import Qt

import pytest

pytestmark = pytest.mark.qt


# ── Sample model data ────────────────────────────────────────────

SAMPLE_MODELS = [
    {"id": "deepseek-v4-flash", "provider": "deepseek",
     "name": "DeepSeek V4 Flash", "contextWindow": 1048576},
    {"id": "deepseek-v4-pro", "provider": "deepseek",
     "name": "DeepSeek V4 Pro", "contextWindow": 1048576},
    {"id": "qwythos-abliterated", "provider": "llama-cpp",
     "name": "Huihui Qwythos 9B Abliterated Q6_K", "contextWindow": 316672},
    {"id": "Gemma-4-E2B-it", "provider": "llama-cpp",
     "name": "Gemma 4 E2B BF16", "contextWindow": 131072},
    {"id": "Nemotron-Nano-9B-v2", "provider": "llama-cpp",
     "name": "NVIDIA Nemotron Nano 9B v2 Q5_K_M", "contextWindow": 131072},
]

ENABLED_IDS = {"deepseek-v4-flash", "qwythos-abliterated", "Gemma-4-E2B-it"}
ALL_MODEL_IDS = {m["id"] for m in SAMPLE_MODELS}


# ── Helpers ───────────────────────────────────────────────────────


def _model_count(tree) -> int:
    """Count leaf (model) items in a tree."""
    total = 0
    for i in range(tree.topLevelItemCount()):
        total += tree.topLevelItem(i).childCount()
    return total


def _model_ids_in_tree(tree) -> set[str]:
    """Collect model IDs from a tree's UserRole data."""
    ids: set[str] = set()
    for i in range(tree.topLevelItemCount()):
        prov = tree.topLevelItem(i)
        for j in range(prov.childCount()):
            child = prov.child(j)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "model":
                ids.add(data["id"])
    return ids


def _visible_model_count(tree) -> int:
    """Count visible (non-hidden) model items in a tree."""
    total = 0
    for i in range(tree.topLevelItemCount()):
        prov = tree.topLevelItem(i)
        if prov.isHidden():
            continue
        for j in range(prov.childCount()):
            if not prov.child(j).isHidden():
                total += 1
    return total


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session (offscreen)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def dialog(qapp):
    """Create a ModelPickerDialog with sample models."""
    from ui.model_dialog import ModelPickerDialog

    dlg = ModelPickerDialog(SAMPLE_MODELS, ENABLED_IDS)
    yield dlg
    dlg.close()


# ═══════════════════════════════════════════════════════════════════
#  Dialog creation
# ═══════════════════════════════════════════════════════════════════


class TestDialogCreation:
    """Verify ModelPickerDialog initializes correctly."""

    def test_creates(self, dialog):
        assert dialog is not None
        assert dialog.windowTitle() == "Select Model"

    def test_has_two_tabs(self, dialog):
        assert dialog._tabs.count() == 2
        assert dialog._tabs.tabText(0) == "All"
        assert dialog._tabs.tabText(1) == "Enabled"


# ═══════════════════════════════════════════════════════════════════
#  All tab
# ═══════════════════════════════════════════════════════════════════


class TestAllTab:
    """"All" tab shows every model regardless of enabled state."""

    def test_shows_all_models(self, dialog):
        assert _model_count(dialog._all_tree) == len(SAMPLE_MODELS)

    def test_all_model_ids_present(self, dialog):
        ids = _model_ids_in_tree(dialog._all_tree)
        assert ids == ALL_MODEL_IDS


# ═══════════════════════════════════════════════════════════════════
#  Enabled tab
# ═══════════════════════════════════════════════════════════════════


class TestEnabledTab:
    """"Enabled" tab shows only models in the enabled_ids set."""

    def test_shows_only_enabled_models(self, dialog):
        ids = _model_ids_in_tree(dialog._enabled_tree)
        assert ids == ENABLED_IDS

    def test_enabled_count_matches(self, dialog):
        assert _model_count(dialog._enabled_tree) == len(ENABLED_IDS)

    def test_disabled_models_excluded(self, dialog):
        ids = _model_ids_in_tree(dialog._enabled_tree)
        disabled = ALL_MODEL_IDS - ENABLED_IDS
        assert ids.isdisjoint(disabled)


# ═══════════════════════════════════════════════════════════════════
#  Selection
# ═══════════════════════════════════════════════════════════════════


class TestSelection:
    """Verify model selection and accessors work."""

    def test_select_model_by_id(self, dialog):
        dialog.select_model("Gemma-4-E2B-it")
        dialog._on_accept()
        assert dialog.selected_model_id == "Gemma-4-E2B-it"
        assert dialog.selected_provider == "llama-cpp"

    def test_select_model_deepseek(self, dialog):
        dialog.select_model("deepseek-v4-flash")
        dialog._on_accept()
        assert dialog.selected_model_id == "deepseek-v4-flash"
        assert dialog.selected_provider == "deepseek"

    def test_reject_clears_selection(self, dialog):
        dialog.select_model("qwythos-abliterated")
        dialog.reject()
        assert dialog.selected_model_id is None
        assert dialog.selected_provider is None


# ═══════════════════════════════════════════════════════════════════
#  Filtering
# ═══════════════════════════════════════════════════════════════════


class TestFilter:
    """Verify the filter narrows the active tab."""

    def test_filter_finds_models_on_all_tab(self, dialog):
        dialog._tabs.setCurrentIndex(0)
        dialog._filter.setText("deepseek")
        assert _visible_model_count(dialog._all_tree) == 2

    def test_filter_finds_model_on_enabled_tab(self, dialog):
        dialog._tabs.setCurrentIndex(1)
        dialog._filter.setText("Gemma")
        assert _visible_model_count(dialog._enabled_tree) == 1

    def test_filter_no_match_shows_none(self, dialog):
        dialog._tabs.setCurrentIndex(0)
        dialog._filter.setText("zzzzzzz")
        assert _visible_model_count(dialog._all_tree) == 0

    def test_empty_filter_shows_all(self, dialog):
        dialog._filter.setText("x")
        dialog._filter.setText("")
        assert _visible_model_count(dialog._all_tree) == len(SAMPLE_MODELS)


# ═══════════════════════════════════════════════════════════════════
#  Provider grouping
# ═══════════════════════════════════════════════════════════════════


class TestProviderGrouping:
    """Verify models are grouped by provider."""

    def test_provider_groups_on_all_tab(self, dialog):
        providers = set()
        for i in range(dialog._all_tree.topLevelItemCount()):
            prov = dialog._all_tree.topLevelItem(i)
            data = prov.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "provider":
                providers.add(data.get("id") or prov.text(0))
        assert "deepseek" in providers
        assert "llama-cpp" in providers

    def test_provider_groups_on_enabled_tab(self, dialog):
        providers = set()
        for i in range(dialog._enabled_tree.topLevelItemCount()):
            prov = dialog._enabled_tree.topLevelItem(i)
            data = prov.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "provider":
                providers.add(data.get("id") or prov.text(0))
        assert "deepseek" in providers
        assert "llama-cpp" in providers
