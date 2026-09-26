"""Tests for src/controller/pi_bridge.py — helper functions and JSON parsing.

Pure-function tests only (no subprocess, no Qt signals).  The RPC event
routing is tested via the _str_content and _extract_text_from_content
helpers that parse pi's message format.
"""

from __future__ import annotations

from typing import Any

import pytest

from controller.pi_bridge import _extract_text_from_content, _str_content


# ═══════════════════════════════════════════════════════════════════
#  _str_content
# ═══════════════════════════════════════════════════════════════════

class TestStrContent:
    """Convert pi message content to plain string."""

    def test_plain_string(self):
        assert _str_content("hello") == "hello"

    def test_empty_string(self):
        assert _str_content("") == ""

    def test_list_of_text_blocks(self):
        blocks = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " world"},
        ]
        assert _str_content(blocks) == "Hello world"

    def test_list_skips_non_text_blocks(self):
        blocks = [
            {"type": "text", "text": "Hello"},
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": " world"},
        ]
        assert _str_content(blocks) == "Hello world"

    def test_list_empty(self):
        assert _str_content([]) == ""

    def test_none(self):
        assert _str_content(None) == "None"

    def test_int(self):
        assert _str_content(42) == "42"


# ═══════════════════════════════════════════════════════════════════
#  _extract_text_from_content
# ═══════════════════════════════════════════════════════════════════

class TestExtractTextFromContent:
    """Extract text from OpenAI-style content arrays."""

    def test_empty(self):
        assert _extract_text_from_content({}) == ""

    def test_missing_content(self):
        assert _extract_text_from_content({"other": "val"}) == ""

    def test_text_blocks(self):
        result = _extract_text_from_content({
            "content": [
                {"type": "text", "text": "Line one "},
                {"type": "text", "text": "Line two"},
            ],
        })
        assert result == "Line one Line two"

    def test_skips_non_text(self):
        result = _extract_text_from_content({
            "content": [
                {"type": "text", "text": "Result: "},
                {"type": "tool_use", "name": "bash"},
                {"type": "text", "text": "done"},
            ],
        })
        assert result == "Result: done"

    def test_non_list_content(self):
        assert _extract_text_from_content({"content": "not a list"}) == ""


# ═══════════════════════════════════════════════════════════════════
#  Streaming block routing
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session (offscreen)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestStreamingBlockRouting:
    """pi labels every chunk with a type and a ``contentIndex``, and delimits
    blocks with ``*_start`` / ``*_end``.  The bridge must preserve that identity
    instead of inferring placement from arrival order."""

    @pytest.fixture
    def bridge(self, qapp):
        from controller.pi_bridge import PiRPCBridge
        return PiRPCBridge()

    @staticmethod
    def _update(at: str, **fields: Any) -> dict[str, Any]:
        return {
            "type": "message_update",
            "assistantMessageEvent": {"type": at, **fields},
        }

    def test_text_events_carry_type_and_index(self, bridge):
        got: list[tuple] = []
        bridge.block_started.connect(lambda i, k, m: got.append(("start", i, k)))
        bridge.block_delta.connect(lambda i, k, d: got.append(("delta", i, k, d)))
        bridge.block_finished.connect(lambda i, k, p: got.append(("end", i, k, p)))

        bridge._route_event(self._update("text_start", contentIndex=0))
        bridge._route_event(self._update("text_delta", contentIndex=0, delta="hi"))
        bridge._route_event(
            self._update("text_end", contentIndex=0, content="hi there")
        )

        assert got == [
            ("start", 0, "reply"),
            ("delta", 0, "reply", "hi"),
            ("end", 0, "reply", "hi there"),
        ]

    def test_interleaved_blocks_keep_their_identity(self, bridge):
        """thinking, toolcall and text in one message must not be conflated."""
        seen: list[tuple] = []
        bridge.block_started.connect(lambda i, k, m: seen.append((i, k, m)))

        bridge._route_event(self._update("thinking_start", contentIndex=0))
        bridge._route_event(self._update(
            "toolcall_start", contentIndex=1, id="call_1", toolName="bash",
        ))
        bridge._route_event(self._update("text_start", contentIndex=2))

        assert seen == [
            (0, "thinking", None),
            (1, "tool", {"id": "call_1", "toolName": "bash"}),
            (2, "reply", None),
        ]

    def test_toolcall_delta_and_end(self, bridge):
        got: list[tuple] = []
        bridge.block_delta.connect(lambda i, k, d: got.append((i, k, d)))
        bridge.block_finished.connect(lambda i, k, p: got.append((i, k, p)))

        bridge._route_event(
            self._update("toolcall_delta", contentIndex=1, delta='{"a":1}')
        )
        bridge._route_event(
            self._update("toolcall_end", contentIndex=1, toolCall={"id": "call_1"})
        )

        assert got == [(1, "tool", '{"a":1}'), (1, "tool", {"id": "call_1"})]

    def test_thinking_end_replaces_buffered_text(self, bridge):
        """``thinking_end`` carries authoritative content for the block."""
        got: list[tuple] = []
        bridge.block_finished.connect(lambda i, k, p: got.append((i, k, p)))
        bridge._route_event(
            self._update("thinking_end", contentIndex=0, content="final reasoning")
        )
        assert got == [(0, "thinking", "final reasoning")]

    def test_message_start_assigns_message_sequence(self, bridge):
        seqs: list[int] = []
        bridge.stream_message_started.connect(lambda s, m: seqs.append(s))
        msg = {"role": "assistant", "content": []}
        bridge._route_event({"type": "message_start", "message": msg})
        bridge._route_event({"type": "message_start", "message": msg})
        assert seqs == [1, 2]

    def test_non_assistant_message_start_is_ignored(self, bridge):
        seqs: list[int] = []
        bridge.stream_message_started.connect(lambda s, m: seqs.append(s))
        bridge._route_event({
            "type": "message_start",
            "message": {"role": "user", "content": "hi"},
        })
        assert seqs == []

    def test_message_end_settles_and_reports_stream_error(self, bridge):
        """Context overflow now arrives as a terminal stopReason on the
        authoritative message, not as a ``done``/``error`` update."""
        settled: list[int] = []
        errors: list[str] = []
        bridge.stream_message_settled.connect(lambda s, m: settled.append(s))
        bridge.error.connect(errors.append)

        msg = {"role": "assistant", "content": []}
        bridge._route_event({"type": "message_start", "message": msg})
        bridge._route_event({"type": "message_end", "message": {
            "role": "assistant", "content": [], "stopReason": "length",
            "errorMessage": "context overflow",
        }})

        assert settled == [1]
        assert errors and "length" in errors[0]
        assert "context overflow" in errors[0]

    def test_message_end_normal_stop_does_not_error(self, bridge):
        errors: list[str] = []
        bridge.error.connect(errors.append)
        bridge._route_event({"type": "message_end", "message": {
            "role": "assistant", "content": [], "stopReason": "toolUse",
        }})
        assert errors == []

    def test_update_without_content_index_warns(self, bridge, capsys):
        """A content update with no block identity is a contract violation and
        must be visible rather than silently misplaced."""
        bridge._route_event(self._update("some_new_type", delta="x"))
        assert "contentIndex" in capsys.readouterr().err
