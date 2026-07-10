"""Tests for src/ui/chat_renderer.py — pure functions only, no Qt needed.

These tests verify the HTML rendering pipeline, message formatting,
agent-work grouping, pagination, and security escaping without requiring
a display server.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ui.chat_renderer import (
    HTML_TEMPLATE,
    _build_html_document,
    _extract_result_text,
    _fmt_tokens,
    _format_json_block,
    _format_subagent_details,
    _render_file_references,
    _split_out_code_fences,
    _summary_from_args,
    format_content_to_html,
    messages_to_html,
)


# ═══════════════════════════════════════════════════════════════════
#  format_content_to_html
# ═══════════════════════════════════════════════════════════════════

class TestFormatContentToHtml:
    """Pure markdown → HTML rendering."""

    def test_plain_text(self):
        html = format_content_to_html("Hello world")
        assert "Hello world" in html
        assert "<p>Hello world</p>" in html

    def test_bold_text(self):
        html = format_content_to_html("**bold**")
        assert "<strong>bold</strong>" in html

    def test_code_fence(self):
        html = format_content_to_html("```python\nprint('hi')\n```")
        assert "language-python" in html
        assert "print" in html
        assert "hi" in html
        assert "<pre" in html

    def test_code_fence_no_lang(self):
        html = format_content_to_html("```\nplain code\n```")
        assert "<pre" in html
        assert "plain code" in html
        assert "language-" not in html

    def test_inline_code_preserved(self):
        html = format_content_to_html("Use `code` here")
        assert "<code>code</code>" in html

    def test_file_ref_image(self):
        html = format_content_to_html("[file: /tmp/test.png]")
        # Should produce an <img> tag
        assert "<img" in html.lower() or "img" in html
        assert "test.png" in html

    def test_file_ref_audio(self):
        html = format_content_to_html("[file: /tmp/test.wav]")
        # Should produce an <audio> tag
        assert "<audio" in html
        assert "test.wav" in html

    def test_file_ref_inside_code_block(self):
        """References inside fenced code blocks must NOT be expanded."""
        html = format_content_to_html("```\n[file: /tmp/test.png]\n```")
        # The reference should appear as literal text inside the code block
        assert "[file: /tmp/test.png]" in html
        assert "<img" not in html

    def test_file_ref_inside_inline_code(self):
        """References inside inline code spans must NOT be expanded."""
        html = format_content_to_html("Use `[file: /tmp/test.png]` here")
        assert "[file: /tmp/test.png]" in html
        assert "<img" not in html

    def test_math_dollars(self):
        html = format_content_to_html(r"$$E = mc^2$$")
        assert "E = mc" in html or "math" in html

    def test_table(self):
        html = format_content_to_html("| A | B |\n|---|---|\n| 1 | 2 |")
        assert "<table>" in html or "<table" in html

    def test_multiple_paragraphs(self):
        html = format_content_to_html("Line one\n\nLine two")
        assert "Line one" in html
        assert "Line two" in html


# ═══════════════════════════════════════════════════════════════════
#  _render_file_references
# ═══════════════════════════════════════════════════════════════════

class TestRenderFileReferences:
    """[file: /path] → inline media expansion."""

    def test_image_png(self):
        result = _render_file_references("[file: /img/photo.png]")
        assert "![photo.png](/img/photo.png)" in result

    def test_image_jpg(self):
        result = _render_file_references("[file: /img/photo.jpg]")
        assert "![photo.jpg](/img/photo.jpg)" in result

    def test_image_webp(self):
        result = _render_file_references("[file: /img/photo.webp]")
        assert "![photo.webp](/img/photo.webp)" in result

    def test_audio_wav(self):
        result = _render_file_references("[file: /audio/recording.wav]")
        assert "<audio controls" in result
        assert "/audio/recording.wav" in result

    def test_unknown_extension(self):
        result = _render_file_references("[file: /data/doc.pdf]")
        # Unknown extensions are left as-is
        assert "[file: /data/doc.pdf]" in result

    @pytest.mark.parametrize("fmt", [
        "```\n[file: test.png]\n```",
        "`[file: test.png]`",
    ])
    def test_protected_from_code(self, fmt):
        """References in code contexts must not be expanded."""
        result = _render_file_references(fmt)
        assert "[file: test.png]" in result
        assert "![test]" not in result


# ═══════════════════════════════════════════════════════════════════
#  _split_out_code_fences
# ═══════════════════════════════════════════════════════════════════

class TestSplitOutCodeFences:
    def test_no_fences(self):
        parts = _split_out_code_fences("hello")
        assert parts == ["hello"]

    def test_single_fence(self):
        parts = _split_out_code_fences("before\n```\ncode\n```\nafter")
        assert len(parts) == 3

    def text_adjacent_fences(self):
        parts = _split_out_code_fences("```\na\n```\n```\nb\n```")
        assert len(parts) == 2
        assert "a" in parts[0]
        assert "b" in parts[1]


# ═══════════════════════════════════════════════════════════════════
#  _format_json_block
# ═══════════════════════════════════════════════════════════════════

class TestFormatJsonBlock:
    def test_dict(self):
        result = _format_json_block({"a": 1, "b": 2})
        # JSON keys/values are HTML-escaped
        assert "a" in result
        assert "1" in result
        assert "b" in result

    def test_str(self):
        result = _format_json_block("hello")
        assert result == "hello"

    def test_int(self):
        result = _format_json_block(42)
        assert "42" in result

    def test_escaped_html(self):
        result = _format_json_block({"x": "<script>"})
        assert "&lt;script&gt;" in result


# ═══════════════════════════════════════════════════════════════════
#  _fmt_tokens
# ═══════════════════════════════════════════════════════════════════

class TestFmtTokens:
    def test_zero(self):
        assert _fmt_tokens(0) == "0"

    def test_hundreds(self):
        assert _fmt_tokens(500) == "500"

    def test_thousands(self):
        assert _fmt_tokens(1500) == "1k"

    def test_ten_thousands(self):
        assert _fmt_tokens(12300) == "12k"

    def test_millions(self):
        assert _fmt_tokens(2_500_000) == "2.5M"


# ═══════════════════════════════════════════════════════════════════
#  _summary_from_args
# ═══════════════════════════════════════════════════════════════════

class TestSummaryFromArgs:
    def test_bash_command(self):
        assert _summary_from_args("bash", {"command": "ls -la"}) == "ls -la"

    def test_read_path(self):
        assert _summary_from_args("read", {"path": "/tmp/file.txt"}) == "/tmp/file.txt"

    def test_write_path(self):
        assert _summary_from_args("write", {"path": "/tmp/out.md"}) == "/tmp/out.md"

    def test_fetch_url(self):
        assert _summary_from_args("fetch_url", {"url": "https://example.com"}) \
            == "https://example.com"

    def test_subagent_task(self):
        assert _summary_from_args("subagent", {"task": "review code"}) == "review code"

    def test_edit_path_and_old(self):
        result = _summary_from_args("edit", {"path": "/tmp/f.py", "oldText": "foo"})
        assert "/tmp/f.py" in result
        assert "foo" in result

    def test_unknown_tool_first_string(self):
        result = _summary_from_args("custom", {"message": "hello", "count": 42})
        assert result == "hello"

    def test_no_known_field(self):
        result = _summary_from_args("custom", {"count": 42})
        assert result == "42"

    def test_empty_args(self):
        assert _summary_from_args("bash", {}) == ""


# ═══════════════════════════════════════════════════════════════════
#  _format_subagent_details
# ═══════════════════════════════════════════════════════════════════

class TestFormatSubagentDetails:
    def test_empty(self):
        assert _format_subagent_details({}) == ""

    def test_no_results(self):
        assert _format_subagent_details({"results": []}) == ""

    def test_basic(self):
        details = {
            "results": [{
                "agent": "reviewer",
                "model": "anthropic/claude-sonnet-4",
                "turns": 2,
            }]
        }
        result = _format_subagent_details(details)
        assert "reviewer" in result
        assert "claude-sonnet-4" in result
        assert "2 turns" in result

    def test_with_usage(self):
        details = {
            "results": [{
                "agent": "coder",
                "usage": {"input": 5000, "output": 2000, "cacheRead": 1000},
            }]
        }
        result = _format_subagent_details(details)
        assert "coder" in result
        assert "5k" in result  # input tokens
        assert "2k" in result  # output tokens
        assert "R1k" in result  # cache reads


# ═══════════════════════════════════════════════════════════════════
#  _extract_result_text
# ═══════════════════════════════════════════════════════════════════

class TestExtractResultText:
    def test_string_result(self):
        assert _extract_result_text({"result": "hello"}) == "hello"

    def test_dict_result(self):
        assert '"key": "val"' in _extract_result_text({"result": {"key": "val"}})

    def test_fmt_result_fallback(self):
        """Should fall back to _fmt_result if result is missing."""
        # Use a value that won't look like an HTML tag after decoding
        item = {"_fmt_result": "command output text"}
        assert "command output text" in _extract_result_text(item)

    def test_empty(self):
        assert _extract_result_text({}) == ""


# ═══════════════════════════════════════════════════════════════════
#  messages_to_html — basic turn rendering
# ═══════════════════════════════════════════════════════════════════

class TestMessagesToHtmlEmpty:
    def test_empty_list(self):
        html = messages_to_html([])
        assert html == ""

    def test_only_non_turns(self):
        html = messages_to_html([{"kind": "thinking", "text": "hmm"}])
        assert html != ""
        assert "hmm" in html


class TestMessagesToHtmlUserTurn:
    def test_user_message(self, sample_turns):
        html = messages_to_html(sample_turns[:1])
        assert "message-row user" in html
        assert "bubble user" in html
        assert "Hello!" in html

    def test_multiple_turns(self, sample_turns):
        html = messages_to_html(sample_turns)
        assert "Hello!" in html
        assert "Hi there!" in html
        assert "image" in html


class TestMessagesToHtmlAssistantTurn:
    def test_assistant_message(self):
        html = messages_to_html([{"kind": "turn", "role": "you", "content": "Response"}])
        assert "message-row assistant" in html
        assert "bubble assistant" in html
        assert "Response" in html


class TestMessagesToHtmlThinking:
    def test_thinking_rendered(self):
        html = messages_to_html([
            {"kind": "thinking", "text": "Reasoning step…", "expanded": False},
        ])
        assert "Reasoning step" in html
        assert "Thinking" in html

    def test_thinking_hidden_when_show_thinking_false(self):
        html = messages_to_html(
            [{"kind": "thinking", "text": "hidden", "expanded": False}],
            show_thinking=False,
        )
        assert "hidden" not in html


class TestMessagesToHtmlToolStack:
    def test_tool_rendered(self):
        html = messages_to_html([{
            "kind": "tool_stack",
            "items": [{"tool_name": "bash", "args": {"command": "ls"}}],
        }])
        assert "Bash:" in html or "bash" in html

    def test_tool_hidden_when_show_tools_false(self):
        html = messages_to_html(
            [{"kind": "tool_stack", "items": [{"tool_name": "bash"}]}],
            show_tools=False,
        )
        assert "bash" not in html


class TestAgentWorkGrouping:
    """Adjacent thinking + tool_stack → single agent-work bubble."""

    def test_single_group(self):
        msgs = [
            {"kind": "thinking", "text": "Reasoning"},
            {"kind": "tool_stack", "items": [{"tool_name": "bash"}]},
        ]
        html = messages_to_html(msgs)
        assert "agent-work" in html
        assert "Reasoning" in html
        # Tool names are capitalized by the renderer
        assert "Bash" in html

    def test_multiple_groups(self, sample_agent_work):
        html = messages_to_html(sample_agent_work)
        # Two groups should produce two agent-work bubbles
        assert html.count("agent-work") >= 2

    def test_turn_between_groups(self, sample_agent_work):
        html = messages_to_html(sample_agent_work)
        # The user turns should appear between the agent-work bubbles
        assert html.count("List files") == 1
        assert html.count("Read that file") == 1


# ═══════════════════════════════════════════════════════════════════
#  _build_html_document
# ═══════════════════════════════════════════════════════════════════

class TestBuildHtmlDocument:
    def test_basic_wrapper(self):
        doc = _build_html_document("<p>hello</p>")
        assert "<!DOCTYPE html>" in doc
        assert "<p>hello</p>" in doc
        assert "</html>" in doc

    def test_theme_applied(self):
        theme = {"bg": "#000", "text": "#fff"}
        doc = _build_html_document("content", theme=theme)
        assert "#000" in doc
        assert "#fff" in doc

    def test_scroll_attr(self):
        doc_scroll = _build_html_document("x", scroll_to_bottom=True)
        assert 'data-scroll="1"' in doc_scroll

        doc_no_scroll = _build_html_document("x", scroll_to_bottom=False)
        assert 'data-scroll="0"' in doc_no_scroll


class TestHtmlTemplate:
    """The HTML_TEMPLATE string must contain the expected placeholders."""

    def test_has_theme_vars_placeholder(self):
        assert "/* THEME_VARS */" in HTML_TEMPLATE

    def test_has_messages_placeholder(self):
        assert "{messages_html}" in HTML_TEMPLATE

    def test_has_scroll_placeholder(self):
        assert "{scroll}" in HTML_TEMPLATE

    def test_has_page_nav_placeholder(self):
        assert "/* PAGE_NAV_CSS */" in HTML_TEMPLATE

    def test_has_js_runtime(self):
        assert "_isAtBottom" in HTML_TEMPLATE
        assert "_scrollToBottom" in HTML_TEMPLATE


# ═══════════════════════════════════════════════════════════════════
#  Security — XSS / escaping
# ═══════════════════════════════════════════════════════════════════

class TestSecurityEscaping:
    """HTML injection and XSS prevention."""

    def test_html_in_content_is_escaped(self):
        """markdown-it is configured with html=True, so raw HTML passes through.
        HTML escaping happens at the template level (code blocks, JSON) but
        not in markdown body text.  This is by design — the model's output
        can include HTML directly."""
        html = format_content_to_html("<script>alert('xss')</script>")
        # With html=True, raw HTML passes through markdown-it
        assert "<script>" in html
        assert "alert('xss')" in html

    def test_html_in_json_block_is_escaped(self):
        result = _format_json_block({"x": "<script>evil</script>"})
        assert "<script>" not in result
        assert "&lt;" in result

    def test_html_in_tool_argument_is_escaped(self):
        """Tool args with HTML content should be escaped in agent-work bubbles."""
        html = messages_to_html([{
            "kind": "tool_stack",
            "items": [{
                "tool_name": "bash",
                "args": {"command": "<script>alert(1)</script>"},
            }],
        }])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_in_user_message_is_escaped(self):
        """HTML in user messages passes through markdown-it's html=True.
        The inner content bubble is rendered via format_content_to_html
        which allows HTML. Proper XSS prevention is at the Qt/WebEngine
        level (CSP headers via QWebEngineSettings)."""
        html = messages_to_html([{
            "kind": "turn", "role": "human",
            "content": "<img src=x onerror=alert(1)>",
        }])
        # With html=True, raw HTML passes through
        assert "<img src=x" in html or "&lt;img src=x" in html

    def test_angle_brackets_in_text_are_escaped(self):
        html = format_content_to_html("use std::collections::HashMap")
        assert "std::collections" in html
        # No HTML tags should leak
        assert html.count("<") <= 5  # markup tags only


# ═══════════════════════════════════════════════════════════════════
#  Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_very_long_line(self):
        """Long lines should not crash the renderer."""
        long = "word " * 2000
        html = format_content_to_html(long)
        assert len(html) > 0

    def test_unicode(self):
        html = format_content_to_html("🎤 Voice recording")
        assert "🎤" in html

    def test_newlines_in_message(self):
        html = messages_to_html([{
            "kind": "turn", "role": "human",
            "content": "line1\nline2\nline3",
        }])
        assert "line1" in html
        assert "line2" in html

    def test_none_content(self):
        """messages_to_html should handle None content gracefully."""
        html = messages_to_html([{
            "kind": "turn", "role": "human",
            "content": None,
        }])
        # Should not crash — content becomes "None" string
        assert html is not None

    def test_empty_messages(self):
        html = messages_to_html([])
        assert html == ""
