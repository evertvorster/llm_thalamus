from __future__ import annotations

from runtime.nodes.context_bootstrap import _build_prefill_calls
from runtime.nodes.llm_primary_agent import _build_primary_agent_messages
from runtime.tools.resources import ToolResources


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubBuilder:
    def render_prompt(self, prompt_name: str) -> str:
        assert prompt_name == "runtime_primary_agent"
        return "SYSTEM CONTRACT\nWORLD\n{\"identity\":{}}\nSTATUS\nok\nEXECUTION STATE\n{}"


def test_context_bootstrap_prefill_uses_configured_limits() -> None:
    state = {"world": {"project": "Alpha", "topics": ["Planning"]}}
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        prefill_chat_history_limit=9,
        prefill_memory_k=13,
    )

    calls = _build_prefill_calls(state=state, resources=resources)

    assert calls == [
        ("chat_history_tail", {"limit": 9}),
        ("openmemory_query", {"query": "Alpha | Planning", "k": 13}),
    ]


def test_primary_agent_transcript_shape_has_no_context_block_message() -> None:
    state = {
        "task": {"user_text": "What do you remember about my family?"},
        "context": {
            "sources": [
                {
                    "kind": "chat_turns",
                    "records": [
                        {"role": "human", "content": "Earlier question"},
                        {"role": "you", "content": "Earlier answer"},
                    ],
                }
            ]
        },
        "runtime": {
            "context_bootstrap_prefill": [
                {
                    "tool_name": "openmemory_query",
                    "args": {"query": "family", "k": 10},
                    "result": {"ok": True, "content": [{"type": "text", "text": "memory result"}]},
                }
            ]
        },
    }

    messages = _build_primary_agent_messages(state, _StubBuilder())

    assert messages[0].role == "system"
    assert "WORLD" in messages[0].content
    assert "STATUS" in messages[0].content
    assert "CONTEXT" not in messages[0].content
    assert "context_apply_ops" not in messages[0].content
    assert "synthetic prefill" not in messages[0].content
    assert "simulated" not in messages[0].content.lower()
    assert [m.role for m in messages[1:]] == ["user", "assistant", "assistant", "tool", "user"]
    assert messages[-1].content == "What do you remember about my family?"
