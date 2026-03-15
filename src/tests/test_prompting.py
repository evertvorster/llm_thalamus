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
    assert "You are the topics extractor and topics list maintainer." in prompt
    assert "PROGRAMMATIC CONTRACT" in prompt
    assert "Your output is consumed programmatically." in prompt
    assert "Natural language is an error." in prompt
    assert "<<RECENT_TURNS_JSON>>" in prompt
    assert "compact retrieval index for future bootstrap memory recall" in prompt
    assert "small rolling set of durable topics" in prompt
    assert "Step 1: Classify the current topic or topics of the USER_MESSAGE" in prompt
    assert "Step 6: Calculate the final list of topics to be stored to the world state." in prompt
    assert "WORLD APPLY OPS RULES" in prompt
    assert "replaces the entire `WORLD.topics` list with the list you provide" in prompt
    assert "Always compute the final complete topics list first." in prompt
    assert "Then call the real `world_apply_ops` tool once to write that final list." in prompt
    assert "Do not try to edit individual topic positions." in prompt
    assert 'If they match, reply with "DONE"' in prompt
    assert "<<AVAILABLE_TOOLS>>" in prompt


def test_runtime_reflect_memory_prompt_teaches_memory_only_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect_memory.txt").read_text(encoding="utf-8")
    assert "Your task is not conversation." in prompt
    assert "store one durable memory per round with `openmemory_store`" in prompt
    assert "finish by replying `DONE`" in prompt
    assert "<<BOOTSTRAP_MEMORY_EVIDENCE_JSON>>" in prompt
    assert "Start with the current `USER_MESSAGE` and the current turn as the primary source of memory candidates." in prompt
    assert "always include `content`" in prompt
    assert "always include `user_id`" in prompt
    assert "Store all clearly durable memories from the turn, but only one per round." in prompt
    assert "Do not treat `BOOTSTRAP MEMORY EVIDENCE` as a memory candidate list to copy back into storage." in prompt
    assert "`type` may only be `contextual`, `factual`, or `both`" in prompt
    assert "if you are unsure, prefer the minimal valid call with only `content` and `user_id`" in prompt
    assert '`{"tool":"openmemory_store","args":{...}}`' in prompt
    assert "Do not update topics in this node." in prompt
    assert "Fake tool JSON is invalid." in prompt
    assert "If you intend to perform an action, call the real tool." in prompt
    assert "If memory review is complete, reply exactly `DONE`." in prompt
    assert "Not allowed:" in prompt
    assert "<<AVAILABLE_TOOLS>>" in prompt


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
    assert "Allowed internal task classes:" in prompt
    assert "`direct_answer`" in prompt
    assert "`retrieval_needed`" in prompt
    assert "`action_needed`" in prompt
    assert "`multi_step_plan`" in prompt
    assert "Keep classification and planning internal unless the user explicitly asks to see a plan." in prompt
