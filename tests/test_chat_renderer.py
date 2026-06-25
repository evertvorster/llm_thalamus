"""Test suite for the chat renderer — pure functions and HTML output.

These tests exercise the module-level functions in ``src/ui/chat_renderer.py``
without requiring a Qt display.  They verify rendering correctness, page
slicing, agent-work grouping, status labels, icon lookups, and the full
HTML document wrapper.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from ui.chat_renderer import (
    HTML_TEMPLATE,
    _build_html_document,
    _fmt_tokens,
    _format_json_block,
    _format_subagent_details,
    _item_summary,
    _tool_icon,
    _tool_item_status_label,
    _tool_item_title,
    format_content_to_html,
    messages_to_html,
)


# ═══════════════════════════════════════════════════════════════════
#  Convenience helpers
# ═══════════════════════════════════════════════════════════════════


def _make_turn(role: str, content: str, meta: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"kind": "turn", "role": role, "content": content}
    if meta:
        msg["meta"] = meta
    return msg


def _make_thinking(text: str, expanded: bool = False) -> dict[str, Any]:
    return {"kind": "thinking", "text": text, "expanded": expanded}


def _make_tool_stack(
    stack_id: str,
    items: list[dict[str, Any]],
    expanded: bool = False,
) -> dict[str, Any]:
    return {"kind": "tool_stack", "stack_id": stack_id, "items": items, "expanded": expanded}


def _make_tool_item(
    tool_call_id: str,
    tool_name: str,
    status: str = "ok",
    expanded: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "status": status,
        "expanded": expanded,
        "item_key": tool_call_id,
    }
    item.update(extra)
    return item


# ═══════════════════════════════════════════════════════════════════
#  Module-level helpers
# ═══════════════════════════════════════════════════════════════════


class TestFormatContentToHtml:
    """Markdown → HTML rendering."""

    def test_bold_and_italic(self):
        html = format_content_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_code_block_python(self):
        html = format_content_to_html('```python\nprint("hello")\n```')
        assert 'class="code-block"' in html
        assert "print" in html
        assert "language-python" in html

    def test_code_block_no_lang(self):
        html = format_content_to_html("```\nplain text\n```")
        assert 'class="code-block"' in html
        assert "plain text" in html

    def test_inline_code(self):
        html = format_content_to_html("use `print()` function")
        assert "<code>print()</code>" in html

    def test_plain_text_passthrough(self):
        html = format_content_to_html("just plain text")
        assert "just plain text" in html

    def test_empty_string(self):
        html = format_content_to_html("")
        assert html == ""

    def test_table(self):
        markdown = "| a | b |\n|---|---|\n| 1 | 2 |"
        html = format_content_to_html(markdown)
        assert "<table>" in html
        assert "<th>a</th>" in html

    def test_multiple_code_blocks(self):
        markdown = '```\nfirst\n```\n\n```\nsecond\n```'
        html = format_content_to_html(markdown)
        assert html.count("code-block") == 2


class TestFormatJsonBlock:
    """JSON / value formatting for <pre> display."""

    def test_plain_string(self):
        assert _format_json_block("hello") == "hello"

    def test_simple_dict(self):
        result = _format_json_block({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_dict_with_html_special_chars(self):
        result = _format_json_block({"cmd": "<script>alert(1)</script>"})
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_nested_dict(self):
        result = _format_json_block({"outer": {"inner": [1, 2, 3]}})
        assert "outer" in result
        assert "inner" in result
        assert "1" in result

    def test_none_value(self):
        result = _format_json_block(None)
        assert "null" in result

    def test_fallback_on_non_serializable(self):
        # object() is not JSON-serializable — falls back to str()
        result = _format_json_block(object())
        assert isinstance(result, str)
        assert len(result) > 0


class TestToolItemStatusLabel:
    """Status → (label, css_class) mapping."""

    @pytest.mark.parametrize(
        "status, expected",
        [
            ("ok", ("complete", "ok")),
            ("error", ("failed", "error")),
            ("running", ("running", "running")),
            ("pending_approval", ("awaiting approval", "pending")),
            ("denied", ("denied", "denied")),
        ],
    )
    def test_known_statuses(self, status, expected):
        assert _tool_item_status_label({"status": status}) == expected

    def test_unknown_status_defaults_to_running(self):
        assert _tool_item_status_label({"status": "unknown"}) == ("running", "running")

    def test_missing_status_defaults_to_running(self):
        assert _tool_item_status_label({}) == ("running", "running")


class TestToolItemTitle:
    """Tool item display name resolution."""

    def test_normal_tool(self):
        assert _tool_item_title({"tool_name": "bash"}) == "bash"

    def test_node_kind_uses_node_id_first(self):
        assert (
            _tool_item_title({"item_kind": "node", "node_id": "nd1", "tool_name": "bash"})
            == "nd1"
        )

    def test_node_kind_falls_back_to_tool_name(self):
        assert _tool_item_title({"item_kind": "node", "tool_name": "read"}) == "read"

    def test_node_kind_falls_back_to_literal_node(self):
        assert _tool_item_title({"item_kind": "node"}) == "node"

    def test_defaults_to_tool(self):
        assert _tool_item_title({}) == "tool"


class TestToolIcon:
    """Tool name → emoji HTML entity."""

    @pytest.mark.parametrize(
        "tool_name, code_point",
        [
            ("bash", "1f5a5"),
            ("read", "1f4c4"),
            ("write", "1f4dd"),
            ("edit", "270f"),
            ("grep", "1f50d"),
            ("find", "1f50e"),
            ("ls", "1f4c1"),
            ("subagent", "1f916"),
        ],
    )
    def test_known_tools(self, tool_name, code_point):
        assert code_point in _tool_icon(tool_name)

    def test_unknown_tool_returns_default(self):
        assert "1f527" in _tool_icon("nonexistent_tool")


class TestFmtTokens:
    """Token count formatting."""

    def test_small_number(self):
        assert _fmt_tokens(42) == "42"

    def test_kilo(self):
        assert _fmt_tokens(5_000) == "5k"

    def test_mega(self):
        assert _fmt_tokens(1_500_000) == "1.5M"

    def test_exact_k(self):
        assert _fmt_tokens(12_000) == "12k"


class TestFormatSubagentDetails:
    """Subagent result details → compact HTML."""

    def test_basic_result(self):
        details = {
            "results": [
                {
                    "agent": "coder",
                    "model": "deepseek/v4-pro",
                    "turns": 3,
                    "usage": {"input": 5000, "output": 1200, "cacheRead": 3000},
                }
            ]
        }
        result = _format_subagent_details(details)
        assert "coder" in result
        assert "v4-pro" in result
        assert "3 turns" in result
        assert "↑5k" in result
        assert "↓1k" in result
        assert "R3k" in result

    def test_empty_results(self):
        assert _format_subagent_details({}) == ""
        assert _format_subagent_details({"results": []}) == ""

    def test_non_list_results(self):
        assert _format_subagent_details({"results": "not a list"}) == ""


class TestItemSummary:
    """Compact preview from structured args, falling back to _fmt_args / _fmt_result."""

    # ── structured args (primary path) ──────────────────────────

    def test_bash_extracts_command(self):
        summary = _item_summary({
            "tool_name": "bash",
            "args": {"command": "ls -la /tmp"},
        })
        assert summary == "ls -la /tmp"

    def test_read_extracts_path(self):
        summary = _item_summary({
            "tool_name": "read",
            "args": {"path": "/home/user/file.md", "limit": 50},
        })
        assert summary == "/home/user/file.md"

    def test_write_extracts_path(self):
        summary = _item_summary({
            "tool_name": "write",
            "args": {"path": "/out.txt", "content": "hello"},
        })
        assert summary == "/out.txt"

    def test_edit_with_short_old_text(self):
        summary = _item_summary({
            "tool_name": "edit",
            "args": {"path": "file.py", "oldText": "print('hi')"},
        })
        # edit gets the special handler: path ← oldText
        assert "file.py" in summary
        assert "print" in summary
        assert "←" in summary

    def test_edit_long_old_text_falls_back_to_path(self):
        long_old = "x" * 100
        summary = _item_summary({
            "tool_name": "edit",
            "args": {"path": "file.py", "oldText": long_old},
        })
        assert summary == "file.py"

    def test_mempalace_search_extracts_query(self):
        summary = _item_summary({
            "tool_name": "mempalace_search",
            "args": {"query": "renderer design", "wing": "llm_thalamus"},
        })
        assert summary == "renderer design"

    def test_subagent_extracts_task(self):
        summary = _item_summary({
            "tool_name": "subagent",
            "args": {"task": "fix the bug in auth.py"},
        })
        assert summary == "fix the bug in auth.py"

    def test_grep_extracts_pattern(self):
        summary = _item_summary({
            "tool_name": "grep",
            "args": {"pattern": "def main"},
        })
        assert summary == "def main"

    def test_unknown_tool_uses_first_string_value(self):
        summary = _item_summary({
            "tool_name": "custom_tool",
            "args": {"url": "https://example.com", "method": "GET"},
        })
        assert summary == "https://example.com"

    def test_unknown_tool_first_numeric_value(self):
        summary = _item_summary({
            "tool_name": "custom_tool",
            "args": {"count": 42},
        })
        assert summary == "42"

    def test_empty_args_dict(self):
        summary = _item_summary({
            "tool_name": "bash",
            "args": {},
        })
        assert summary == ""

    # ── fallback: _fmt_args ─────────────────────────────────────

    def test_fallback_to_fmt_args(self):
        summary = _item_summary({
            "_fmt_args": "plain text command",
        })
        assert summary == "plain text command"

    def test_fmt_args_html_entity_decoding(self):
        summary = _item_summary({
            "_fmt_args": "{&quot;command&quot;: &quot;ls -la&quot;}",
        })
        # Should decode entities and extract "ls -la"
        assert summary == "ls -la"

    def test_fmt_args_strips_tags(self):
        summary = _item_summary({
            "_fmt_args": '<span class="x">command</span>',
        })
        assert summary == "command"
        assert "<span" not in summary

    # ── fallback: _fmt_result ───────────────────────────────────

    def test_fallback_to_fmt_result(self):
        summary = _item_summary({
            "_fmt_result": "total 48\ndrwxr-xr-x",
        })
        # Takes first line only
        assert summary == "total 48"

    def test_fmt_result_html_entity_decoding(self):
        summary = _item_summary({
            "_fmt_result": "&lt;html&gt;output&lt;/html&gt;",
        })
        # Entities decoded, then HTML tags stripped → plain text
        assert summary == "output"

    # ── edge cases ──────────────────────────────────────────────

    def test_empty(self):
        assert _item_summary({}) == ""

    def test_non_string_fmt_args(self):
        assert _item_summary({"_fmt_args": 123}) == ""

    def test_truncation(self):
        long_text = "x" * 200
        summary = _item_summary({"args": {"command": long_text}})
        assert len(summary) <= 180

    def test_args_none(self):
        summary = _item_summary({"tool_name": "bash", "args": None})
        assert summary == ""


# ═══════════════════════════════════════════════════════════════════
#  messages_to_html() — singular messages
# ═══════════════════════════════════════════════════════════════════


class TestMessagesToHtmlEmpty:
    def test_empty_list(self):
        assert messages_to_html([]) == ""

    def test_with_page_args(self):
        assert messages_to_html([], page_start=0, page_end=0) == ""


class TestMessagesToHtmlUserTurn:
    """User (human) message rendering."""

    def test_simple_user_turn(self):
        html = messages_to_html([_make_turn("human", "Hello world")])
        assert 'class="message-row user"' in html
        assert "Hello world" in html

    def test_user_turn_with_meta(self):
        html = messages_to_html([
            _make_turn("human", "Hi", meta="2026-06-25 10:00")
        ])
        assert 'class="meta"' in html
        assert "2026-06-25 10:00" in html

    def test_user_turn_markdown_rendered(self):
        html = messages_to_html([_make_turn("human", "**bold** text")])
        assert "<strong>bold</strong>" in html


class TestMessagesToHtmlAssistantTurn:
    """Assistant (you) message rendering."""

    def test_simple_assistant_turn(self):
        html = messages_to_html([_make_turn("you", "I can help")])
        assert 'class="message-row assistant"' in html
        assert "I can help" in html

    def test_last_turn_gets_latest_class(self):
        html = messages_to_html([_make_turn("you", "final reply")])
        assert "bubble assistant latest" in html

    def test_middle_turn_no_latest(self):
        msgs = [
            _make_turn("you", "first"),
            _make_turn("human", "second"),
        ]
        html = messages_to_html(msgs, page_start=0, page_end=1)
        assert "latest" not in html

    def test_assistant_code_block_rendered(self):
        html = messages_to_html([
            _make_turn("you", '```\nsome code\n```')
        ])
        assert "code-block" in html


class TestMessagesToHtmlThinking:
    """Thinking / reasoning bubble rendering."""

    def test_collapsed_by_default(self):
        html = messages_to_html([_make_thinking("reasoning...")])
        assert "thinking-row" in html
        assert "thinking-card" in html
        assert "reasoning..." in html
        assert 'style="display:none"' in html or "display:none" in html
        assert 'Show"' in html or "Show<" in html

    def test_expanded(self):
        html = messages_to_html([_make_thinking("visible", expanded=True)])
        assert "visible" in html
        assert 'Hide"' in html or "Hide<" in html

    def test_streaming_target_id(self):
        msg = {"kind": "thinking", "text": "live...", "expanded": True}
        html = messages_to_html([msg], thinking_stream_index=0)
        assert 'id="thinking-stream-content-0"' in html


class TestMessagesToHtmlToolStack:
    """Tool execution stack rendering."""

    def test_single_item_collapsed(self):
        msgs = [
            _make_tool_stack("call_x", [
                _make_tool_item("call_x", "bash", _fmt_args="ls -la"),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "tool-stack-row" in html
        assert "tool-stack-card" in html
        assert "bash" in html
        assert "agent-work-group" in html  # auto-wrapped

    def test_multi_item(self):
        msgs = [
            _make_tool_stack("multi", [
                _make_tool_item("a", "bash", status="ok", _fmt_args="cmd-a"),
                _make_tool_item("b", "read", status="error", _fmt_args="cmd-b"),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "bash" in html
        assert "read" in html
        assert "tool-stack-badge ok" in html
        assert "tool-stack-badge error" in html

    def test_error_status_shows_error_text(self):
        msgs = [
            _make_tool_stack("err", [
                _make_tool_item(
                    "err", "bash", status="error", error="command not found",
                    _fmt_args="bad cmd",
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "failed" in html
        assert "command not found" in html

    def test_pending_approval(self):
        msgs = [
            _make_tool_stack("pend", [
                _make_tool_item(
                    "pend", "bash", status="pending_approval", expanded=True,
                    request_id="req1", description="Dangerous command",
                    _fmt_args="rm -rf /",
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "awaiting approval" in html
        assert "Dangerous command" in html
        assert "thalamus://tool-approval" in html
        assert "Approve once" in html
        assert "Deny once" in html

    def test_pending_approval_mcp_with_always_allow(self):
        msgs = [
            _make_tool_stack("pend", [
                _make_tool_item(
                    "pend", "mcp_tool", status="pending_approval", expanded=True,
                    request_id="req1", tool_kind="mcp", mcp_server_id="srv1",
                    _fmt_args="{}",
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "Always allow" in html
        assert "Always deny" in html

    def test_expanded_tool_shows_arguments_and_output(self):
        msgs = [
            _make_tool_stack("exp", [
                _make_tool_item(
                    "exp", "bash", status="ok", expanded=True,
                    _fmt_args=_format_json_block({"command": "ls"}),
                    _fmt_result=_format_json_block("file1\nfile2"),
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "Arguments" in html
        assert "Output" in html
        assert "ls" in html
        assert "file1" in html

    def test_tool_with_details(self):
        details_html = _format_subagent_details({
            "results": [
                {"agent": "coder", "model": "deepseek/v4", "turns": 1,
                 "usage": {"input": 100, "output": 50, "cacheRead": 0}},
            ],
        })
        msgs = [
            _make_tool_stack("sub", [
                _make_tool_item(
                    "sub", "subagent", expanded=True,
                    _fmt_details=details_html, _fmt_args="task",
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "coder" in html

    def test_meta_line(self):
        msgs = [
            _make_tool_stack("meta", [
                _make_tool_item(
                    "meta", "bash", tool_kind="mcp", mcp_server_id="srv",
                    step=1, _fmt_args="cmd",
                ),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "tool-stack-item-meta" in html
        assert "mcp" in html
        assert "srv" in html
        assert "step 1" in html


# ═══════════════════════════════════════════════════════════════════
#  Agent work grouping
# ═══════════════════════════════════════════════════════════════════


class TestAgentWorkGrouping:
    """Automatic wrapping of consecutive non-turn messages."""

    def test_single_thinking_wrapped(self):
        html = messages_to_html([_make_thinking("think")])
        assert "agent-work-group" in html

    def test_multiple_thinkings_in_one_group(self):
        msgs = [_make_thinking("t1"), _make_thinking("t2"), _make_thinking("t3")]
        html = messages_to_html(msgs)
        # Should be ONE group wrapping three items
        items_count = html.count("thinking-row")
        assert items_count == 3
        assert "Agent work (3 items)" in html

    def test_thinking_and_tool_in_same_group(self):
        msgs = [
            _make_thinking("think"),
            _make_tool_stack("call", [
                _make_tool_item("call", "bash", _fmt_args="cmd"),
            ]),
        ]
        html = messages_to_html(msgs)
        assert "Agent work (2 items)" in html

    def test_group_resets_after_turn(self):
        msgs = [
            _make_thinking("before"),
            _make_turn("you", "answer"),
            _make_thinking("after"),
        ]
        html = messages_to_html(msgs)
        assert html.count("agent-work-group") == 2

    def test_last_group_expanded(self):
        msgs = [
            _make_thinking("t1"),
            _make_turn("you", "reply"),
            _make_thinking("t2", expanded=False),
        ]
        html = messages_to_html(msgs)
        # The last group should be expanded (▼ not ▶)
        groups = re.findall(r'agent-work-group\s+(expanded|collapsed)', html)
        assert groups[-1] == "expanded"

    def test_streaming_group_expanded(self):
        msgs = [_make_thinking("live", expanded=True)]
        html = messages_to_html(msgs, thinking_stream_index=0)
        assert "expanded" in html

    def test_group_with_header_icon(self):
        msgs = [_make_thinking("think")]
        html = messages_to_html(msgs)
        assert "▶" in html or "▼" in html  # either collapsed or expanded icon


# ═══════════════════════════════════════════════════════════════════
#  Page slicing
# ═══════════════════════════════════════════════════════════════════


class TestPageSlicing:
    """Rendering subsets of the message list."""

    def test_slice_start_only(self):
        msgs = [
            _make_turn("human", "Q1"),
            _make_thinking("think"),
            _make_turn("you", "A1"),
            _make_turn("human", "Q2"),
            _make_turn("you", "A2"),
        ]
        # [0:2) → human Q1 + thinking (but NOT assistant A1 at idx 2)
        html = messages_to_html(msgs, page_start=0, page_end=2)
        assert "Q1" in html
        assert "think" in html
        assert "A1" not in html
        assert "Q2" not in html

    def test_slice_middle(self):
        msgs = [
            _make_turn("human", "Q1"),
            _make_turn("you", "A1"),
            _make_turn("human", "Q2"),
            _make_turn("you", "A2"),
        ]
        html = messages_to_html(msgs, page_start=2, page_end=4)
        assert "Q2" in html
        assert "A2" in html
        assert "Q1" not in html

    def test_page_end_none_renders_all(self):
        msgs = [
            _make_turn("human", "Q1"),
            _make_turn("you", "A1"),
        ]
        html = messages_to_html(msgs)
        assert "Q1" in html
        assert "A1" in html

    def test_slice_assistant_stream(self):
        msgs = [
            _make_turn("human", "Q"),
            _make_turn("you", "streaming..."),
        ]
        html = messages_to_html(msgs, assistant_stream_index=1)
        assert 'id="assistant-stream-content"' in html

    def test_no_streaming_when_index_out_of_slice(self):
        msgs = [
            _make_turn("you", "first"),
            _make_turn("you", "second"),
        ]
        # streaming index 1 but slice is [0:1)
        html = messages_to_html(msgs, assistant_stream_index=1, page_start=0, page_end=1)
        assert 'id="assistant-stream-content"' not in html

    def test_tools_follow_their_user_message_in_slice(self):
        msgs = [
            _make_turn("human", "Q"),
            _make_thinking("think"),
            _make_tool_stack("t", [_make_tool_item("t", "bash", _fmt_args="x")]),
            _make_turn("you", "A"),
        ]
        # Slice [0:4) includes Q, thinking, tool — they stay together
        html = messages_to_html(msgs, page_start=0, page_end=4)
        assert "Q" in html
        assert "think" in html
        assert "bash" in html
        assert "A" in html


# ═══════════════════════════════════════════════════════════════════
#  _build_html_document()
# ═══════════════════════════════════════════════════════════════════


class TestBuildHtmlDocument:
    """Full HTML document wrapper."""

    def test_doctype_present(self):
        doc = _build_html_document("<p>hello</p>")
        assert doc.startswith("<!DOCTYPE html>")

    def test_inner_html_inserted(self):
        doc = _build_html_document("<div>test</div>")
        assert "<div>test</div>" in doc

    def test_chat_container_present(self):
        doc = _build_html_document("")
        assert 'class="chat-container"' in doc

    def test_default_theme_vars(self):
        doc = _build_html_document("")
        assert "--bg: #f5f5f7;" in doc
        assert "--text: #000000;" in doc
        assert "--bubble-user: #e3f2fd;" in doc

    def test_custom_theme_overrides(self):
        doc = _build_html_document("", theme={"bg": "#111", "text": "#eee"})
        assert "--bg: #111;" in doc
        assert "--text: #eee;" in doc

    def test_theme_ignores_invalid_keys(self):
        doc = _build_html_document("", theme={"nonexistent": "#f00"})
        assert "nonexistent" not in doc

    def test_theme_ignores_non_hex_values(self):
        doc = _build_html_document("", theme={"bg": "rgb(1,2,3)"})
        assert "--bg: #f5f5f7;" in doc  # stayed default

    def test_scroll_to_bottom_true(self):
        doc = _build_html_document("", scroll_to_bottom=True)
        assert 'data-scroll="1"' in doc

    def test_scroll_to_bottom_false(self):
        doc = _build_html_document("", scroll_to_bottom=False)
        assert 'data-scroll="0"' in doc

    def test_page_nav_css_included(self):
        doc = _build_html_document("")
        assert "page-divider" in doc
        assert "page-nav-prev" in doc

    def test_js_runtime_included(self):
        doc = _build_html_document("")
        assert "_isAtBottom" in doc
        assert "_scrollToBottom" in doc
        assert "_beginAssistantBubble" in doc
        assert "_appendToolCard" in doc
        assert "renderMathNodes" in doc
        assert "enhanceCodeBlocks" in doc

    def test_kaTeX_loaded(self):
        doc = _build_html_document("")
        assert "katex.min.css" in doc
        assert "katex.min.js" in doc

    def test_highlight_js_loaded(self):
        doc = _build_html_document("")
        assert "highlight.min.js" in doc


# ═══════════════════════════════════════════════════════════════════
#  HTML_TEMPLATE structure
# ═══════════════════════════════════════════════════════════════════


class TestHtmlTemplate:
    """Structural integrity of the HTML_TEMPLATE string."""

    def test_messages_placeholder(self):
        assert "{messages_html}" in HTML_TEMPLATE

    def test_scroll_placeholder(self):
        assert "{scroll}" in HTML_TEMPLATE

    def test_theme_vars_placeholder(self):
        assert "/* THEME_VARS */" in HTML_TEMPLATE

    def test_page_nav_placeholder(self):
        assert "/* PAGE_NAV_CSS */" in HTML_TEMPLATE

    def test_has_body_tag(self):
        assert "<body" in HTML_TEMPLATE

    def test_has_data_ready_attribute(self):
        assert 'data-ready="0"' in HTML_TEMPLATE

    def test_dom_content_loaded_handler(self):
        assert "DOMContentLoaded" in HTML_TEMPLATE


# ═══════════════════════════════════════════════════════════════════
#  Realistic integration scenarios
# ═══════════════════════════════════════════════════════════════════


class TestRealisticSession:
    """End-to-end rendering of realistic session data."""

    def test_full_conversation_with_tools(self):
        """Simulate a typical agent turn: thinking → tools → assistant."""
        msgs = [
            _make_turn("human", "What files are in this directory?"),
            _make_thinking("I should run ls", expanded=False),
            _make_tool_stack("call_bash", [
                _make_tool_item(
                    "call_bash", "bash", status="ok",
                    _fmt_args=_format_json_block({"command": "ls -la"}),
                    _fmt_result=_format_json_block("file1.txt\nfile2.py\n"),
                ),
            ]),
            _make_turn("you", "Here are the files I found:\n\n- file1.txt\n- file2.py"),
        ]
        html = messages_to_html(msgs)

        assert "What files are in this directory?" in html
        assert "I should run ls" in html
        assert "bash" in html
        assert "ls -la" in html
        assert "file1.txt" in html
        assert "agent-work-group" in html
        assert "tool-stack-badge ok" in html

    def test_tool_summary_shows_human_readable_command(self):
        """The tool item summary shows the actual command, not escaped JSON.

        This is the critical regression test for the bug where tool call
        cards showed blank/garbled text instead of the command.
        """
        item = _make_tool_item(
            "call_bash", "bash", status="ok",
            args={"command": "ls -la /tmp"},
            _fmt_args=_format_json_block({"command": "ls -la /tmp"}),
        )
        msgs = [
            _make_turn("human", "List files"),
            _make_tool_stack("call_bash", [item]),
        ]
        html = messages_to_html(msgs)

        # The summary span should contain the actual command.
        assert 'tool-stack-item-summary' in html
        # Extract summary content between the summary span tags.
        summary_match = re.search(
            r'<span class="tool-stack-item-summary">(.*?)</span>', html
        )
        assert summary_match is not None, "summary span missing"
        summary_text = summary_match.group(1)
        assert "ls -la /tmp" in summary_text, (
            f"summary should show the command, got: {summary_text}"
        )
        # The summary should NOT contain escaped JSON artifacts.
        assert "&quot;command&quot;" not in summary_text

    def test_tool_summary_mempalace_search(self):
        item = _make_tool_item(
            "call_mem", "mempalace_search", status="ok",
            args={"query": "renderer design", "wing": "llm_thalamus", "limit": 10},
            _fmt_args=_format_json_block({
                "query": "renderer design", "wing": "llm_thalamus", "limit": 10,
            }),
        )
        msgs = [
            _make_turn("human", "Search memories"),
            _make_tool_stack("call_mem", [item]),
        ]
        html = messages_to_html(msgs)
        assert "renderer design" in html

    def test_tool_summary_read_file(self):
        item = _make_tool_item(
            "call_read", "read", status="ok",
            args={"path": "/home/user/config.json", "limit": 50},
            _fmt_args=_format_json_block({"path": "/home/user/config.json", "limit": 50}),
        )
        msgs = [
            _make_turn("human", "Read config"),
            _make_tool_stack("call_read", [item]),
        ]
        html = messages_to_html(msgs)
        assert "/home/user/config.json" in html

    def test_tool_summary_edit_file(self):
        item = _make_tool_item(
            "call_edit", "edit", status="ok",
            args={"path": "src/main.py", "oldText": "def run():", "newText": "def main():"},
            _fmt_args=_format_json_block({
                "path": "src/main.py", "oldText": "def run():",
            }),
        )
        msgs = [
            _make_turn("human", "Edit file"),
            _make_tool_stack("call_edit", [item]),
        ]
        html = messages_to_html(msgs)
        assert "src/main.py" in html
        assert "←" in html
        assert "def run():" in html

    def test_multiple_turns_with_errors(self):
        msgs = [
            _make_turn("human", "Run command A"),
            _make_thinking("running A"),
            _make_tool_stack("call_a", [
                _make_tool_item("call_a", "bash", status="ok", _fmt_args="cmd a"),
            ]),
            _make_turn("you", "A succeeded"),
            _make_turn("human", "Run command B"),
            _make_thinking("running B"),
            _make_tool_stack("call_b", [
                _make_tool_item(
                    "call_b", "bash", status="error", error="permission denied",
                    _fmt_args="cmd b",
                ),
            ]),
            _make_turn("you", "B failed"),
        ]
        html = messages_to_html(msgs)

        # Two separate agent-work groups
        assert html.count("agent-work-group") == 2
        assert "complete" in html  # first tool succeeded
        assert "failed" in html    # second tool failed
        assert "permission denied" in html

    def test_many_tools_in_one_turn(self):
        """Multiple parallel tool calls in the same assistant turn."""
        items = []
        for i, (name, cmd) in enumerate([
            ("bash", "ls"), ("read", "file.md"), ("grep", "pattern"),
        ]):
            items.append(_make_tool_item(
                f"call_{i}", name, _fmt_args=_format_json_block({"command": cmd}),
            ))
        msgs = [
            _make_turn("human", "Do several things"),
            _make_thinking("I need to run several tools"),
            _make_tool_stack("multi", items),
            _make_turn("you", "Done"),
        ]
        html = messages_to_html(msgs)

        assert "bash" in html
        assert "read" in html
        assert "grep" in html
        assert "Agent work (2 items)" in html  # thinking + 1 tool stack

    def test_session_with_subagent(self):
        msgs = [
            _make_turn("human", "Dispatch coder"),
            _make_thinking("Dispatching subagent"),
            _make_tool_stack("sub", [
                _make_tool_item(
                    "sub", "subagent", expanded=True,
                    _fmt_args=_format_json_block({"task": "fix the bug"}),
                    _fmt_result=_format_json_block("Fixed the bug in file.py"),
                    _fmt_details=_format_subagent_details({
                        "results": [
                            {"agent": "coder", "model": "deepseek/v4-pro",
                             "turns": 5,
                             "usage": {"input": 10000, "output": 2000, "cacheRead": 5000}},
                        ],
                    }),
                ),
            ]),
            _make_turn("you", "Subagent completed"),
        ]
        html = messages_to_html(msgs)

        assert "subagent" in html
        assert "coder" in html
        assert "v4-pro" in html
        assert "5 turns" in html

    def test_empty_session(self):
        html = messages_to_html([])
        assert html == ""

    def test_session_with_only_assistant(self):
        msgs = [_make_turn("you", "Hello! How can I help?")]
        html = messages_to_html(msgs)
        assert "Hello! How can I help?" in html


# ═══════════════════════════════════════════════════════════════════
#  Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Boundary conditions and unexpected inputs."""

    def test_thinking_with_empty_text(self):
        html = messages_to_html([_make_thinking("")])
        assert "thinking-row" in html
        # Should not crash or produce broken HTML

    def test_tool_stack_without_items(self):
        html = messages_to_html([_make_tool_stack("empty", [])])
        # Should not crash
        assert isinstance(html, str)

    def test_turn_with_empty_content(self):
        html = messages_to_html([_make_turn("human", "")])
        assert "message-row" in html

    def test_message_with_unknown_kind(self):
        msg = {"kind": "weird_unknown", "content": "hi"}
        html = messages_to_html([msg])
        # Defaults to "turn" per the code
        assert isinstance(html, str)

    def test_message_with_missing_kind(self):
        msg = {"role": "human", "content": "hi"}
        html = messages_to_html([msg])
        assert "hi" in html

    def test_tool_item_unusable_summary(self):
        """Item with no usable _fmt_args or _fmt_result should not crash."""
        item = _make_tool_item("x", "bash")
        html = messages_to_html([
            _make_tool_stack("x", [item])
        ])
        assert isinstance(html, str)

    def test_tool_item_very_long_output(self):
        long_text = "a" * 5000
        item = _make_tool_item("x", "bash", _fmt_result=long_text)
        html = messages_to_html([
            _make_tool_stack("x", [item])
        ])
        assert long_text in html

    def test_meta_html_escaping(self):
        html = messages_to_html([
            _make_turn("human", "hi", meta='<script>alert(1)</script>')
        ])
        assert "&lt;script&gt;" in html
        assert "<script>" not in html

    def test_tool_name_html_escaping(self):
        item = _make_tool_item("x", "<b>bold</b>", _fmt_args="cmd")
        html = messages_to_html([
            _make_tool_stack("x", [item])
        ])
        assert "&lt;b&gt;" in html
        assert "<b>bold</b>" not in html


# ═══════════════════════════════════════════════════════════════════
#  Security / escaping
# ═══════════════════════════════════════════════════════════════════


class TestSecurityEscaping:
    """XSS prevention and HTML escaping."""

    def test_user_content_preserved(self):
        """Markdown-it with html:True passes raw HTML through.

        This is standard markdown-it behaviour and matches the pre-rewrite
        renderer.  For llm-thalamus (a local desktop app rendering the
        user's own pi session transcripts), this is acceptable.
        """
        html = messages_to_html([
            _make_turn("human", '<b>bold</b>')
        ])
        # Raw HTML is preserved by markdown-it (html: True)
        assert '<b>bold</b>' in html

    def test_script_tag_passes_through(self):
        """<script> tags pass through because markdown-it html:True.

        Note: this is by-design for the markdown renderer.  The content
        originates from local pi session transcripts, not from
        untrusted external sources.
        """
        html = messages_to_html([
            _make_turn("human", '<script>alert(1)</script>')
        ])
        # The script tag appears as-is (markdown-it html:True)
        assert '<script>alert(1)</script>' in html

    def test_tool_args_escaped(self):
        item = _make_tool_item(
            "x", "bash",
            _fmt_args=_format_json_block({"command": "<script>bad</script>"}),
        )
        html = messages_to_html([_make_tool_stack("x", [item])])
        assert "&lt;script&gt;" in html

    def test_thinking_text_escaped(self):
        msgs = [_make_thinking('<img src=x onerror=alert(1)>')]
        html = messages_to_html(msgs)
        assert "&lt;img" in html
        assert "<img " not in html
