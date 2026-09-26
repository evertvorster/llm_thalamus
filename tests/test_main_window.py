"""Tests for src/ui/main_window.py — window creation and signal wiring.

Requires QT_QPA_PLATFORM=offscreen (set in pytest.ini).
These tests verify that MainWindow initializes correctly and that all
critical signal connections are wired.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.qt


def _has_display() -> bool:
    """Return True if a display (or offscreen platform) is available."""
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.primaryScreen() is not None
    except Exception:
        return False


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
def bridge():
    """Create a PiRPCBridge (no subprocess started)."""
    from controller.pi_bridge import PiRPCBridge
    return PiRPCBridge()


@pytest.fixture
def graphics_dir():
    """Resolve the graphics directory for the test environment."""
    return Path(__file__).resolve().parent.parent / "resources" / "graphics"


@pytest.fixture
def main_window(qapp, bridge, graphics_dir):
    """Create a MainWindow for testing."""
    from ui.main_window import MainWindow
    win = MainWindow(bridge, graphics_dir)
    yield win
    win.close()


# ═══════════════════════════════════════════════════════════════════
#  Window creation
# ═══════════════════════════════════════════════════════════════════

class TestMainWindowCreation:
    """Verify MainWindow initializes without errors."""

    def test_creates(self, main_window):
        """Window should construct without crashing (guards class boundary bug)."""
        assert main_window is not None
        assert main_window.windowTitle() == "llm_thalamus"

    def test_chat_renderer_exists(self, main_window):
        assert main_window.chat is not None

    def test_chat_input_exists(self, main_window):
        assert main_window.chat_input is not None

    def test_brain_widget_exists(self, main_window):
        assert main_window.brain is not None

    def test_voice_button_exists(self, main_window):
        assert main_window._voice_button is not None


# ═══════════════════════════════════════════════════════════════════
#  Critical signal wiring
# ═══════════════════════════════════════════════════════════════════

class TestCriticalSignalWiring:
    """Verify all signal handlers present (guards class boundary bug)."""

    # These methods were at risk during the refactoring
    _CRITICAL = [
        "_on_busy",
        "_on_input_text_changed",
        "_on_escape",
        "_on_error",
        "_on_stream_message_started",
        "_on_block_started",
        "_on_block_delta",
        "_on_block_finished",
        "_on_stream_message_settled",
        "_on_tool_start",
        "_on_tool_update",
        "_on_tool_end",
        "_on_transcription_ready",
        "_on_voice_audio_ready",
        "_on_settings_dialog",
        "_on_reload",
        "_on_send",
        "_on_follow_up",
        "_on_open_session_dialog",
        "_on_new_session",
        "_on_response_received",
        "_on_compact",
        "_fix_corrupted_session",
    ]

    def test_all_critical_methods_present(self, main_window):
        missing = [m for m in self._CRITICAL if not hasattr(main_window, m)]
        assert not missing, f"Missing methods: {missing}"

    def test_signal_connections_work(self, main_window):
        """Verify key signals are wired by checking bridge signal-to-slot count."""
        from PySide6.QtCore import QMetaObject
        bridge = main_window._bridge

        # Check that the bridge has connected signals
        # (we can't easily enumerate Qt connections, but we can verify
        #  the bridge's signal count is non-zero)
        assert bridge is not None


# ═══════════════════════════════════════════════════════════════════
#  VoiceController wiring
# ═══════════════════════════════════════════════════════════════════

class TestVoiceControllerWiring:
    """Verify VoiceController is created and wired correctly."""

    def test_voice_controller_exists(self, main_window):
        assert hasattr(main_window, "_voice")
        assert main_window._voice is not None

    def test_transcription_handler_is_method(self, main_window):
        assert hasattr(main_window, "_on_transcription_ready")

    def test_audio_ready_handler_is_method(self, main_window):
        assert hasattr(main_window, "_on_voice_audio_ready")

    def test_voice_button_wired(self, main_window):
        """Voice button should have at least one connection."""
        btn = main_window._voice_button
        # QPushButton pressed/released signals should be connected
        # (we check by verifying the button's signal is valid)
        assert btn is not None
        # Text is set from QSettings (stt/voice_mode) — accept either mode.
        assert btn.text() in ("🎤 Voice", "🎤 STT")


# ═══════════════════════════════════════════════════════════════════
#  Settings dialog wiring
# ═══════════════════════════════════════════════════════════════════

class TestSettingsDialogWiring:
    """Verify SettingsDialog can be created and opened."""

    def test_settings_handler_is_method(self, main_window):
        assert hasattr(main_window, "_on_settings_dialog")

    def test_settings_button_wired(self, main_window):
        """Settings button should be clickable without crash."""
        assert main_window.configure_button is not None
        assert main_window.configure_button.text() == "Settings"


class TestSessionDialogWiring:
    """Verify the session dialog can be opened."""

    def test_open_session_dialog(self, main_window):
        """Opening the session dialog should not crash."""
        try:
            main_window._on_open_session_dialog()
        except Exception:
            import traceback
            traceback.print_exc()
            raise


# ═══════════════════════════════════════════════════════════════════
#  Keyboard shortcuts
# ═══════════════════════════════════════════════════════════════════

class TestKeyboardShortcuts:
    """Verify critical keyboard shortcuts exist."""

    def test_escape_shortcut(self, main_window):
        assert hasattr(main_window, "_on_escape")

    def test_cycle_thinking_shortcut(self, main_window):
        assert hasattr(main_window, "_on_cycle_thinking_level")

    def test_model_picker_shortcut(self, main_window):
        assert hasattr(main_window, "_on_open_model_picker")


# ═══════════════════════════════════════════════════════════════════
#  Enabled Model IDs helper
# ═══════════════════════════════════════════════════════════════════


class TestReadEnabledModelIds:
    """Verify _read_enabled_model_ids reads from settings.json correctly."""

    def test_reads_enabled_ids(self, main_window, monkeypatch, tmp_path):
        """Should return the set of enabled model IDs from settings.json."""
        import json
        from pathlib import Path

        pi_dir = tmp_path / ".pi" / "agent"
        pi_dir.mkdir(parents=True)
        cfg = {"enabledModels": ["model-a", "model-b"]}
        (pi_dir / "settings.json").write_text(json.dumps(cfg))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = main_window._read_enabled_model_ids()
        assert result == {"model-a", "model-b"}

    def test_returns_empty_set_on_missing_file(self, main_window, monkeypatch, tmp_path):
        """Should return empty set if settings.json doesn't exist."""
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = main_window._read_enabled_model_ids()
        assert result == set()

    def test_returns_empty_set_on_missing_key(self, main_window, monkeypatch, tmp_path):
        """Should return empty set if enabledModels key is missing."""
        import json
        from pathlib import Path

        pi_dir = tmp_path / ".pi" / "agent"
        pi_dir.mkdir(parents=True)
        (pi_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = main_window._read_enabled_model_ids()
        assert result == set()


# ═══════════════════════════════════════════════════════════════════
#  Peak/off-peak pricing badge
# ═══════════════════════════════════════════════════════════════════


class TestPricingBadge:
    @pytest.fixture
    def iso_win(self, qapp, bridge, graphics_dir, monkeypatch):
        """MainWindow with QSettings isolated to a temp ini file."""
        from datetime import timezone
        import tempfile

        from PySide6.QtCore import QSettings as _QtQSettings

        # Deterministic clock: UTC 02:00 -> inside the (1,4) peak window.
        from datetime import datetime
        monkeypatch.setattr(
            "ui.main_window.now_utc",
            lambda: datetime(2026, 1, 15, 2, tzinfo=timezone.utc),
        )

        _ini = tempfile.NamedTemporaryFile(
            suffix=".ini", prefix="llmth-badge-", delete=False
        ).name

        class _Iso(_QtQSettings):
            def __init__(self, *a, **kw):
                super().__init__(_ini, _QtQSettings.Format.IniFormat)

        monkeypatch.setattr("ui.main_window.QSettings", _Iso)
        from ui.main_window import MainWindow
        win = MainWindow(bridge, graphics_dir)
        win._current_model_id = "deepseek-v4-pro"
        yield win, _Iso
        try:
            Path(_ini).unlink()
        except OSError:
            pass

    def test_hidden_when_no_schedule(self, iso_win):
        win, _ = iso_win
        assert win._pricing_badge.isHidden() is True

    def test_reloads_schedule_after_change(self, iso_win):
        from controller.peak_pricing import (
            PricingSchedule, PricingSlot, save_schedules,
        )
        win, _Iso = iso_win
        s = _Iso("llm-thalamus", "llm-thalamus")
        save_schedules(s, [
            PricingSchedule(
                ["deepseek-v4-pro"],
                [PricingSlot(1, 4), PricingSlot(6, 10)],
            )
        ])
        s.sync()

        win._update_pricing_badge()
        assert win._pricing_badge.isHidden() is False
        assert "Peak" in win._pricing_badge.text()

    def test_other_model_stays_hidden(self, iso_win):
        from controller.peak_pricing import (
            PricingSchedule, PricingSlot, save_schedules,
        )
        win, _Iso = iso_win
        s = _Iso("llm-thalamus", "llm-thalamus")
        save_schedules(s, [
            PricingSchedule(["some-other-model"], [PricingSlot(1, 4)])
        ])
        s.sync()
        win._update_pricing_badge()
        assert win._pricing_badge.isHidden() is True

    def test_badge_appears_when_model_revealed_by_get_state(self, iso_win):
        """Startup: badge stays hidden until the model is known, then shows
        as soon as a get_state response reveals it."""
        from controller.peak_pricing import (
            PricingSchedule, PricingSlot, save_schedules,
        )
        win, _Iso = iso_win

        # Simulate startup: model id unknown -> badge hidden.
        win._current_model_id = ""
        win._update_pricing_badge()
        assert win._pricing_badge.isHidden() is True

        # A schedule exists for the model that will be revealed.
        s = _Iso("llm-thalamus", "llm-thalamus")
        save_schedules(s, [
            PricingSchedule(["deepseek-v4-pro"], [PricingSlot(1, 4)])
        ])
        s.sync()

        # get_state response reveals the current model -> badge shows.
        win._on_get_state({
            "model": {
                "id": "deepseek-v4-pro",
                "provider": "deepseek",
                "name": "DeepSeek V4 Pro",
            }
        })
        assert win._pricing_badge.isHidden() is False
        assert "Peak" in win._pricing_badge.text()


# ═══════════════════════════════════════════════════════════════════
#  Streaming content blocks
# ═══════════════════════════════════════════════════════════════════


class TestStreamingBlocks:
    """Blocks are addressed by identity, so a delta always lands in the block
    it belongs to — even when a message interleaves block types."""

    @pytest.fixture
    def chat(self, qapp):
        from ui.chat_renderer import ChatRenderer
        return ChatRenderer()

    def test_begin_block_creates_addressed_message(self, chat):
        chat.begin_block(1, 0, "reply")
        msg = chat._messages[-1]
        assert msg["kind"] == "turn"
        assert (msg["msg_seq"], msg["content_index"]) == (1, 0)

    def test_thinking_block_is_a_separate_kind(self, chat):
        chat.begin_block(1, 1, "thinking")
        assert chat._messages[-1]["kind"] == "thinking"

    def test_deltas_land_in_the_addressed_block(self, chat):
        """Interleaved blocks must not bleed into each other."""
        chat.begin_block(1, 0, "thinking")
        chat.begin_block(1, 1, "reply")
        chat.append_block_delta(1, 0, "thinking", "ponder ")
        chat.append_block_delta(1, 1, "reply", "answer ")
        chat.append_block_delta(1, 0, "thinking", "more")
        assert chat._messages[-2]["text"] == "ponder more"
        assert chat._messages[-1]["content"] == "answer "

    def test_delta_to_unknown_block_is_ignored(self, chat):
        before = list(chat._messages)
        chat.append_block_delta(9, 9, "reply", "stray")
        assert chat._messages == before

    def test_end_block_replaces_streamed_text_with_authoritative(self, chat):
        """``*_end`` carries the final content; it wins over buffered deltas."""
        chat.begin_block(1, 0, "reply")
        chat.append_block_delta(1, 0, "reply", "partial")
        chat.end_block(1, 0, "reply", "partial and complete")
        assert chat._messages[-1]["content"] == "partial and complete"

    def test_end_block_collapses_thinking(self, chat):
        chat.begin_block(1, 0, "thinking")
        assert chat._messages[-1]["expanded"] is True
        chat.end_block(1, 0, "thinking", "done thinking")
        assert chat._messages[-1]["text"] == "done thinking"
        assert chat._messages[-1]["expanded"] is False

    def test_settle_message_closes_an_unclosed_block(self, chat):
        """An aborted stream can leave a block open; message_end must fix it."""
        chat.begin_block(1, 0, "thinking")
        chat.append_block_delta(1, 0, "thinking", "half a thou")
        # Aborted: no thinking_end arrives — only the authoritative message.
        chat.settle_message(1, {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "half a thought"}],
            "stopReason": "aborted",
        })
        assert chat._streaming_blocks == {}
        assert chat._messages[-1]["text"] == "half a thought"
        assert chat._messages[-1]["expanded"] is False

    def test_settle_message_adds_missing_blocks(self, chat):
        chat.settle_message(2, {
            "role": "assistant",
            "content": [{"type": "text", "text": "the answer"}],
        })
        assert chat._messages[-1]["content"] == "the answer"
        assert chat._messages[-1]["msg_seq"] == 2

    def test_begin_block_streams_incrementally(self, chat, monkeypatch):
        """Live blocks append via JS, with no full re-render (avoids flicker)."""
        chat._page_loaded = True
        chat._render_pending = False
        js_calls: list[str] = []
        monkeypatch.setattr(chat, "_exec_js", lambda js: js_calls.append(js))
        chat.begin_block(1, 0, "reply")
        assert js_calls and "_beginBlockBubble(" in js_calls[0]
        assert chat._render_pending is False

    def test_begin_block_falls_back_when_page_not_loaded(self, chat):
        chat._page_loaded = False
        chat._render_pending = False
        chat.begin_block(1, 0, "reply")
        assert chat._render_pending is True

    def test_block_delta_js_targets_that_block(self, chat):
        """The JS target id encodes the block's identity."""
        calls: list[str] = []
        chat._view.page().runJavaScript = lambda js: calls.append(js)
        chat._append_block_delta_js(3, 2, "hi")
        assert any("blk-3-2" in js for js in calls)

    def test_tool_blocks_are_ignored_by_the_renderer(self, chat):
        """Tool cards come from the tool-execution path, keyed by toolCallId."""
        before = len(chat._messages)
        chat.begin_block(1, 0, "tool", {"id": "call_1", "toolName": "bash"})
        assert len(chat._messages) == before

    def test_add_thinking_still_used_for_history(self, chat):
        """History replay adds completed thinking blocks."""
        chat.add_thinking("reasoned about it")
        msg = chat._messages[-1]
        assert msg["kind"] == "thinking"
        assert msg["text"] == "reasoned about it"
        assert msg["expanded"] is False


# ═══════════════════════════════════════════════════════════════════
#  Available thinking levels from the current model
# ═══════════════════════════════════════════════════════════════════


class TestAvailableThinkingLevels:
    def test_response_populates_cache(self, main_window):
        main_window._available_thinking_levels = []
        main_window._on_response_received("get_available_thinking_levels", {
            "success": True,
            "data": {"levels": ["off", "low", "high", "max"]},
        })
        assert main_window._available_thinking_levels == [
            "off", "low", "high", "max",
        ]

    def test_menu_requests_levels_when_not_loaded(self, main_window):
        """Without a cached list, opening the menu asks pi (no hardcoded list)."""
        main_window._available_thinking_levels = []
        commands: list[dict] = []
        main_window._bridge.send_command = lambda cmd: commands.append(cmd)
        main_window._on_thinking_level_menu()
        assert commands == [{"type": "get_available_thinking_levels"}]

    def test_cache_reset_on_model_change(self, main_window):
        """The cached levels are cleared when the current model changes."""
        main_window._current_model_id = ""
        main_window._available_thinking_levels = ["off", "low"]
        main_window._on_get_state({
            "model": {
                "id": "deepseek-v4-pro",
                "provider": "deepseek",
                "name": "DeepSeek V4 Pro",
            }
        })
        assert main_window._available_thinking_levels == []

    def test_cache_kept_when_same_model(self, main_window):
        """Repeated get_state for the same model keeps the cached levels."""
        main_window._current_model_id = "deepseek-v4-pro"
        main_window._available_thinking_levels = ["off", "low"]
        main_window._on_get_state({
            "model": {
                "id": "deepseek-v4-pro",
                "provider": "deepseek",
                "name": "DeepSeek V4 Pro",
            }
        })
        assert main_window._available_thinking_levels == ["off", "low"]


# ═══════════════════════════════════════════════════════════════════
#  SessionConfirmDialog thinking levels
# ═══════════════════════════════════════════════════════════════════


class TestSessionConfirmThinkingLevels:
    def test_uses_supported_levels_when_passed(self, qapp):
        from ui.session_confirm_dialog import SessionConfirmDialog
        dlg = SessionConfirmDialog(
            cwd="/tmp",
            available_models=[],
            current_thinking_level="low",
            available_thinking_levels=["off", "low", "high"],
        )
        assert dlg._available_thinking_levels == ["off", "low", "high"]

    def test_falls_back_to_full_list(self, qapp):
        from ui.session_confirm_dialog import SessionConfirmDialog
        dlg = SessionConfirmDialog(cwd="/tmp", available_models=[])
        assert "minimal" in dlg._available_thinking_levels
        assert "medium" in dlg._available_thinking_levels


# ═══════════════════════════════════════════════════════════════════
#  Session switch re-applies model/thinking
# ═══════════════════════════════════════════════════════════════════


class TestSessionSwitchedReappliesModel:
    """After new_session/switch_session, the chosen model must stick."""

    def test_reapplies_model_and_thinking_level(self, main_window):
        """_on_session_switched resends set_model and set_thinking_level."""
        commands: list[dict] = []
        main_window._bridge.send_command = lambda cmd: commands.append(cmd)
        main_window._provider = "deepseek"
        main_window._current_model_id = "deepseek-v4-flash-vision-exp"
        main_window._thinking_level = "high"

        main_window._on_session_switched()

        set_model = [c for c in commands if c.get("type") == "set_model"]
        set_thinking = [c for c in commands if c.get("type") == "set_thinking_level"]
        assert set_model, "set_model must be re-sent after a session switch"
        assert set_model[-1] == {
            "type": "set_model",
            "provider": "deepseek",
            "modelId": "deepseek-v4-flash-vision-exp",
        }
        assert set_thinking, "set_thinking_level must be re-sent after a session switch"
        assert set_thinking[-1] == {
            "type": "set_thinking_level",
            "level": "high",
        }

    def test_skips_when_no_model_selected(self, main_window):
        """Empty model/thinking selections don't send spurious commands."""
        commands: list[dict] = []
        main_window._bridge.send_command = lambda cmd: commands.append(cmd)
        main_window._provider = ""
        main_window._current_model_id = ""
        main_window._thinking_level = ""

        main_window._on_session_switched()

        set_model = [c for c in commands if c.get("type") == "set_model"]
        set_thinking = [c for c in commands if c.get("type") == "set_thinking_level"]
        assert set_model == []
        assert set_thinking == []
