from __future__ import annotations

from pathlib import Path

import pytest

from runtime.prompting import render_tokens
from runtime.nodes_common import TokenBuilder
from runtime.tool_loop import ToolSet
from runtime.tools.descriptor import ToolDescriptor


def test_render_tokens_normal_substitution() -> None:
    result = render_tokens("Node: <<NODE_ID>>", {"NODE_ID": "answer"})
    assert result == "Node: answer"


def test_render_tokens_raises_for_unresolved_template_token() -> None:
    with pytest.raises(RuntimeError, match=r"<<ROLE_KEY>>"):
        render_tokens(
            "Node: <<NODE_ID>> Role: <<ROLE_KEY>>",
            {"NODE_ID": "answer"},
        )


def test_render_tokens_treats_inserted_text_as_opaque() -> None:
    result = render_tokens(
        "World:\n<<WORLD_JSON>>",
        {"WORLD_JSON": '{"text": "literal <<NODE_ID>> marker"}'},
    )
    assert result == 'World:\n{"text": "literal <<NODE_ID>> marker"}'


def test_render_tokens_does_not_mutate_inserted_values_in_later_passes() -> None:
    result = render_tokens(
        "<<A>> <<B>>",
        {
            "A": "literal <<B>>",
            "B": "final",
        },
    )
    assert result == "literal <<B>> final"

def test_runtime_reflect_topics_prompt_teaches_topic_only_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect_topics.txt").read_text(encoding="utf-8")
    assert "You are the topic-maintenance controller for a completed turn." in prompt
    assert "You do not answer the user." in prompt
    assert "Use only real tool calls." in prompt
    assert "call `world_apply_ops`" in prompt
    assert "reply exactly `DONE`" in prompt


def test_runtime_reflect_memory_prompt_teaches_memory_only_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect_memory.txt").read_text(encoding="utf-8")
    assert "You are the durable-memory maintenance controller for a completed turn." in prompt
    assert "You do not answer the user." in prompt
    assert "Use only real tool calls." in prompt
    assert "call `openmemory_store`" in prompt
    assert "reply exactly `DONE`" in prompt
    assert "Store at most one durable memory per round." in prompt
    assert "Prefer no-op over duplicate or near-duplicate storage." in prompt


def test_token_builder_renders_live_tool_descriptions_into_prompt() -> None:
    class _StubDeps:
        @staticmethod
        def load_prompt(prompt_name: str) -> str:
            assert prompt_name == "runtime_reflect_memory"
            return "<<AVAILABLE_TOOLS>>"

    toolset = ToolSet(
        defs=[],
        handlers={},
        descriptors={
            "openmemory_store": ToolDescriptor(
                public_name="openmemory_store",
                description="Store a durable memory entry in OpenMemory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                    "required": ["content", "user_id"],
                },
                kind="mcp",
                server_id="openmemory",
                remote_name="openmemory_store",
            )
        },
    )

    prompt = TokenBuilder({}, _StubDeps(), node_id="llm.reflect_memory", role_key="reflect", toolset=toolset).render_prompt(
        "runtime_reflect_memory"
    )

    assert "AVAILABLE TOOLS" in prompt
    assert "TOOL: openmemory_store" in prompt
    assert "Store a durable memory entry in OpenMemory." in prompt
    assert '"required": ["content", "user_id"]' in prompt


def test_runtime_primary_agent_prompt_teaches_internal_classification() -> None:
    prompt = Path("resources/prompts/runtime_primary_agent.txt").read_text(encoding="utf-8")
    assert "You are the active assistant for this session." in prompt
    assert "The available tools in this run are real and directly callable by you." in prompt
    assert "Use available tools when needed." in prompt
    assert "Treat tool results as authoritative evidence." in prompt
    assert "call the real tool instead of describing it." in prompt
    assert "call `answer_user` with the exact final reply" in prompt
    assert "Do not answer the user with plain assistant prose." in prompt
    assert "Do not emit fake tool JSON." in prompt
    assert "using only real tool calls in this controller loop" in prompt


def test_runtime_primary_agent_task_prompt_teaches_single_action_selection() -> None:
    prompt = Path("resources/prompts/runtime_primary_agent_task.txt").read_text(encoding="utf-8")
    assert "Latest user request:" in prompt
    assert "<<USER_MESSAGE>>" in prompt
    assert "call exactly one real tool" in prompt
    assert "call `answer_user` exactly once" in prompt
