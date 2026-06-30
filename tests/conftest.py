"""pytest configuration for llm-thalamus tests.

Tests requiring Qt run with QT_QPA_PLATFORM=offscreen (set in pyproject.toml
or via pytest.ini).  Pure-function tests in test_chat_renderer.py and
test_pi_bridge.py need no display.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ── Renderer test helpers ─────────────────────────────────────────

def make_turn(role: str, content: str, **kw: Any) -> dict[str, Any]:
    """Build a turn message dict."""
    msg: dict[str, Any] = {"kind": "turn", "role": role, "content": content}
    msg.update(kw)
    return msg


def make_thinking(text: str = "", expanded: bool = False) -> dict[str, Any]:
    """Build a thinking message dict."""
    return {"kind": "thinking", "text": text, "expanded": expanded}


def make_tool_stack(stack_id: str, items: list[dict] | None = None) -> dict[str, Any]:
    """Build a tool_stack message dict."""
    return {"kind": "tool_stack", "stack_id": stack_id, "items": items or []}


def make_tool_item(
    tool_call_id: str = "",
    tool_name: str = "bash",
    args: dict | None = None,
    status: str = "",
    result: str = "",
    error: str = "",
    tool_kind: str | None = None,
) -> dict[str, Any]:
    """Build a tool_stack item dict."""
    item: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
    }
    if args is not None:
        item["args"] = args
    if status:
        item["status"] = status
    if result:
        item["result"] = result
    if error:
        item["error"] = error
    if tool_kind:
        item["tool_kind"] = tool_kind
    return item


@pytest.fixture
def sample_turns() -> list[dict[str, Any]]:
    """A short realistic message sequence for rendering tests."""
    return [
        make_turn("human", "Hello!"),
        make_turn("you", "Hi there! How can I help?"),
        make_turn("human", "What's in this image?"),
    ]


@pytest.fixture
def sample_agent_work() -> list[dict[str, Any]]:
    """Message sequence with thinking and tool stacks between turns."""
    return [
        make_turn("human", "List files"),
        make_thinking("Let me check the current directory…"),
        make_tool_stack("s1", [
            make_tool_item("t1", "bash", {"command": "ls -la"}, "ok", "total 42\n-rw-r--r-- 1 …"),
        ]),
        make_turn("you", "Here are the files:"),
        make_turn("human", "Read that file"),
        make_thinking("Opening file…"),
        make_tool_stack("s2", [
            make_tool_item("t2", "read", {"path": "/tmp/test.txt"}, "ok", "file content"),
        ]),
        make_turn("you", "Here's the content:"),
    ]
