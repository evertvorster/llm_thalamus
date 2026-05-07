from __future__ import annotations

from runtime.nodes.llm_reflect_memory import (
    DEFAULT_ROOM,
    DEFAULT_WING,
    MEMORY_TOOL_NAME,
    _conversation_drawer_content,
    _drawer_args,
)


def test_reflect_memory_builds_verbatim_conversation_drawer_content() -> None:
    state = {
        "task": {"user_text": "Please remember the exact phrasing."},
        "runtime": {"turn_id": "abc123", "now_iso": "2026-05-07T03:00:00+02:00"},
        "final": {"answer": "I will store this exchange verbatim."},
    }

    content = _conversation_drawer_content(state)

    assert "type: conversation_exchange" in content
    assert "turn_id: abc123" in content
    assert "timestamp: 2026-05-07T03:00:00+02:00" in content
    assert "human:\nPlease remember the exact phrasing." in content
    assert "assistant:\nI will store this exchange verbatim." in content


def test_reflect_memory_drawer_args_target_dora_sessions() -> None:
    state = {
        "task": {"user_text": "Hello"},
        "runtime": {"turn_id": "turn-1"},
        "final": {"answer": "Hi"},
    }

    args = _drawer_args(state)

    assert args["wing"] == DEFAULT_WING == "dora"
    assert args["room"] == DEFAULT_ROOM == "sessions"
    assert args["source_file"] == "llm_thalamus/turn-1.md"
    assert args["added_by"] == "llm_thalamus"
    assert "human:\nHello" in args["content"]
    assert "assistant:\nHi" in args["content"]


def test_reflect_memory_uses_mempalace_add_drawer_tool_name() -> None:
    assert MEMORY_TOOL_NAME == "mempalace_add_drawer"
