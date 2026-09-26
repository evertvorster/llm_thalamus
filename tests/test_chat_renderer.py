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
    _render_raw_activity_bubble,
    _bucket_count,
    _icon_strip_reserve,
    _page_controls_html,
    _page_divider_html,
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


class TestAgentWorkAttachesToTurn:
    """Agent work belongs to the turn that follows it, as that bubble's icon
    strip — it does not get a row of its own."""

    def test_work_before_a_turn_lands_in_that_bubble(self, sample_agent_work):
        html = messages_to_html(sample_agent_work)
        # Both replies carry icons...
        assert html.count("has-icons") == 2
        # ...and no agent-work block is a row of its own any more.  The sections
        # are bare, so they carry no bubble wrapper to be a row.
        assert html.count("bubble-detail-section") == 4
        assert '<div class="message-row agent-work"' not in html

    def test_icon_badges_name_each_category(self, sample_agent_work):
        html = messages_to_html(sample_agent_work)
        assert 'data-target="thinking"' in html
        assert 'data-target="tool_stack"' in html
        assert html.count("bubble-icon-count") >= 4

    def test_trailing_work_with_no_following_turn_still_renders(self):
        msgs = [
            {"kind": "thinking", "text": "Reasoning"},
            {"kind": "tool_stack", "items": [{"tool_name": "bash"}]},
        ]
        html = messages_to_html(msgs)
        assert '<div class="message-row agent-work"' in html
        assert "Reasoning" in html
        # Tool names are capitalized by the renderer
        assert "Bash" in html
        assert "has-icons" not in html

    def test_turns_are_still_separate_bubbles(self, sample_agent_work):
        html = messages_to_html(sample_agent_work)
        assert html.count("List files") == 1
        assert html.count("Read that file") == 1

    def test_show_flags_drop_a_category(self, sample_agent_work):
        html = messages_to_html(sample_agent_work, show_thinking=False)
        assert 'data-target="thinking"' not in html
        assert 'data-target="tool_stack"' in html

    def test_strip_reserve_does_not_grow_with_categories(self, sample_agent_work):
        """The icons stack vertically under the Copy button, so one slot covers
        the strip however many categories a turn has."""
        html = messages_to_html(sample_agent_work)
        assert f"padding-right: {_icon_strip_reserve()}px" in html


# ═══════════════════════════════════════════════════════════════════
#  Collapse state of agent-work items
# ═══════════════════════════════════════════════════════════════════

class TestItemCollapse:
    """Items are a collapsed, scannable list by default.  While the agent is
    mid-turn the newest thinking block and newest tool call stay open, so you
    can watch what is happening now without the transcript growing behind it.
    """

    MSGS = [
        {"kind": "thinking", "text": "first thought"},
        {"kind": "tool_stack", "items": [
            {"tool_name": "bash", "args": {"command": "ls"}, "status": "ok"},
        ]},
        {"kind": "thinking", "text": "second thought"},
        {"kind": "tool_stack", "items": [
            {"tool_name": "read", "args": {"path": "/a"}, "status": "ok"},
            {"tool_name": "edit", "args": {"path": "/b"}, "status": "ok"},
        ]},
    ]

    def test_settled_detail_is_fully_collapsed(self):
        assert _render_raw_activity_bubble(
            self.MSGS, only="thinking"
        ).count("aw-thinking-collapsed") == 2
        assert _render_raw_activity_bubble(
            self.MSGS, only="tool_stack"
        ).count("aw-tool-collapsed") == 3

    def test_live_trailing_work_keeps_the_tail_open(self):
        html = messages_to_html(self.MSGS, live=True)
        # One of two thinking blocks open, one of three tool cards open.
        assert html.count("aw-thinking-collapsed") == 1
        assert html.count("aw-tool-collapsed") == 2
        # And it is the newest of each that stays visible.
        assert 'class="aw-thinking">' in html

    def test_not_live_collapses_the_trailing_work_too(self):
        html = messages_to_html(self.MSGS)
        assert html.count("aw-thinking-collapsed") == 2
        assert html.count("aw-tool-collapsed") == 3

    def test_a_arriving_reply_collapses_everything(self):
        """Once the reply starts, the work moves into its icon strip and folds
        away entirely — nothing stays expanded behind the answer."""
        msgs = self.MSGS + [{"kind": "turn", "role": "you", "content": "Done"}]
        html = messages_to_html(msgs, live=True)
        assert html.count("has-icons") == 1
        assert html.count("aw-thinking-collapsed") == 2
        assert html.count("aw-tool-collapsed") == 3


# ═══════════════════════════════════════════════════════════════════
#  Per-category sections (the compacted view's detail)
# ═══════════════════════════════════════════════════════════════════

class TestCategorySections:
    """``only`` renders a single category, which is how the compacted view
    builds one section per bucket."""

    MIXED = [
        {"kind": "thinking", "text": "Reasoning here"},
        {"kind": "tool_stack", "items": [{"tool_name": "bash"}]},
        {"kind": "activity", "content": "Compaction ran"},
    ]

    def test_only_thinking_excludes_the_others(self):
        html = _render_raw_activity_bubble(self.MIXED, only="thinking")
        assert "Reasoning here" in html
        assert "Bash" not in html
        assert "Compaction ran" not in html

    def test_only_tools_excludes_the_others(self):
        html = _render_raw_activity_bubble(self.MIXED, only="tool_stack")
        assert "Bash" in html
        assert "Reasoning here" not in html
        assert "Compaction ran" not in html

    def test_only_notices_excludes_the_others(self):
        html = _render_raw_activity_bubble(self.MIXED, only="activity")
        assert "Compaction ran" in html
        assert "Reasoning here" not in html
        assert "Bash" not in html

    def test_bare_omits_the_bubble_wrapper(self):
        """The icon already names the category, so a section must not carry a
        second header — nor a nested .bubble, which would pick up a Copy button
        of its own."""
        wrapped = _render_raw_activity_bubble(self.MIXED, only="thinking")
        bare = _render_raw_activity_bubble(self.MIXED, only="thinking", bare=True)
        assert "message-row agent-work" in wrapped
        assert "agent-work-title" in wrapped
        assert "message-row" not in bare
        assert "agent-work-title" not in bare
        assert "bubble" not in bare
        assert "Reasoning here" in bare

    def test_empty_category_renders_nothing(self):
        only_tools = [m for m in self.MIXED if m["kind"] == "tool_stack"]
        assert _render_raw_activity_bubble(only_tools, only="thinking") == ""

    def test_unfiltered_behaviour_is_unchanged(self):
        """No ``only`` still produces one bubble, counting everything."""
        html = _render_raw_activity_bubble(self.MIXED)
        assert "Agent work (3)" in html
        assert "Reasoning here" in html
        assert "Bash" in html
        assert "Compaction ran" in html

    def test_bucket_count_matches_render(self):
        """The icon badge and its detail must agree, or they drift."""
        msgs = [
            *self.MIXED,
            {"kind": "thinking", "text": ""},          # empty → not counted
            {"kind": "activity", "content": "   "},     # blank → not counted
            {"kind": "tool_stack", "items": [
                {"tool_name": "read"}, {"tool_name": "edit"},
            ]},
        ]
        total = sum(
            _bucket_count(k, msgs)
            for k in ("thinking", "tool_stack", "activity")
        )
        # The unfiltered title counts exactly what the buckets total.
        assert f"Agent work ({total})" in _render_raw_activity_bubble(msgs)


class TestNestedToolsAndIconOnlyTurns:
    """Two Stage 3 details: nesting has to be visible in a headers-only list,
    and a turn with no prose has to look deliberate rather than broken."""

    SUBAGENT = [{
        "kind": "tool_stack",
        "items": [{
            "tool_name": "subagent",
            "args": {"agent": "scout"},
            "status": "ok",
            "details": {"results": [{"toolCalls": [
                {"text": "read a.py", "expandedText": "contents a"},
                {"text": "read b.py", "expandedText": "contents b"},
            ]}]},
        }],
    }]

    def test_subagent_header_reports_nested_count(self):
        html = _render_raw_activity_bubble(self.SUBAGENT, only="tool_stack")
        assert "Subagent: scout" in html
        # The list shows headers only, so nesting must be visible unopened.
        assert "2 nested" in html

    def test_nested_cards_are_collapsed_with_the_parent(self):
        html = _render_raw_activity_bubble(self.SUBAGENT, only="tool_stack")
        # Parent plus its two nested calls, all collapsed.
        assert html.count("aw-tool-collapsed") == 3
        assert "read a.py" in html

    def test_subagent_without_nesting_says_nothing_extra(self):
        msgs = [{"kind": "tool_stack", "items": [
            {"tool_name": "subagent", "args": {"agent": "scout"},
             "status": "ok", "details": {"results": [{"toolCalls": []}]}},
        ]}]
        html = _render_raw_activity_bubble(msgs, only="tool_stack")
        assert "Subagent: scout" in html
        assert "nested" not in html

    def test_icon_only_turn_is_marked(self):
        msgs = [
            {"kind": "turn", "role": "human", "content": "go"},
            {"kind": "thinking", "text": "hmm"},
            {"kind": "turn", "role": "you", "content": ""},
        ]
        html = messages_to_html(msgs)
        assert "has-icons" in html
        assert "icons-only" in html

    def test_turn_with_prose_is_not_icon_only(self):
        msgs = [
            {"kind": "turn", "role": "human", "content": "go"},
            {"kind": "thinking", "text": "hmm"},
            {"kind": "turn", "role": "you", "content": "answer"},
        ]
        html = messages_to_html(msgs)
        assert "has-icons" in html
        assert "icons-only" not in html

    def test_a_turn_with_neither_prose_nor_work_is_plain(self):
        msgs = [{"kind": "turn", "role": "you", "content": ""}]
        html = messages_to_html(msgs)
        assert "has-icons" not in html
        assert "icons-only" not in html


# ═══════════════════════════════════════════════════════════════════
#  Page navigation
# ═══════════════════════════════════════════════════════════════════

class TestPageNav:
    """Page boundaries stay in the transcript; the controls float, because an
    in-flow nav moves every time a bubble is drawn above it."""

    def test_divider_carries_no_controls(self):
        divider = _page_divider_html()
        assert "page-divider" in divider
        assert "page-nav" not in divider
        assert "<input" not in divider

    def test_controls_carry_no_divider(self):
        controls = _page_controls_html(0, 1, 3)
        assert "page-nav-float" in controls
        assert "page-divider" not in controls

    def test_controls_label_the_visible_range(self):
        assert "Pages 1\u20132 / 3" in _page_controls_html(0, 1, 3)
        assert "Page 2 / 3" in _page_controls_html(1, 1, 3)

    def test_controls_hide_unavailable_directions(self):
        first = _page_controls_html(0, 0, 3)
        last = _page_controls_html(2, 2, 3)
        # Hidden rather than omitted, so the bar does not jump about.
        assert "visibility:hidden" in first
        assert "visibility:hidden" in last


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
        """An empty attribute means "no instruction": the page decides from
        what it remembered, rather than being told to jump to the bottom."""
        doc_scroll = _build_html_document("x", scroll_to_bottom=True)
        assert 'data-scroll="1"' in doc_scroll

        doc_no_scroll = _build_html_document("x", scroll_to_bottom=False)
        assert 'data-scroll=""' in doc_no_scroll
        assert 'data-scroll="0"' not in doc_no_scroll


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
