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
