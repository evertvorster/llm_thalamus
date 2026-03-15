from __future__ import annotations

from pathlib import Path

import pytest

from runtime.prompting import render_tokens


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
    assert "Your task is not conversation." in prompt
    assert "review and update `WORLD.topics`" in prompt
    assert "finish by replying `DONE`" in prompt
    assert "<<RECENT_TURNS_JSON>>" in prompt
    assert "compact retrieval index for future bootstrap memory recall" in prompt
    assert "do not leave `WORLD.topics` empty when durable recurring topics are clearly visible" in prompt
    assert "Fake tool JSON is invalid." in prompt
    assert "If you intend to perform an action, call the real tool." in prompt
    assert "Do not store memory in this node." in prompt
    assert "If topic maintenance is complete, reply exactly `DONE`." in prompt
    assert "Not allowed:" in prompt


def test_runtime_reflect_memory_prompt_teaches_memory_only_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect_memory.txt").read_text(encoding="utf-8")
    assert "Your task is not conversation." in prompt
    assert "store one durable memory per round with `openmemory_store`" in prompt
    assert "finish by replying `DONE`" in prompt
    assert "<<BOOTSTRAP_MEMORY_EVIDENCE_JSON>>" in prompt
    assert "always include `content`" in prompt
    assert "always include `user_id`" in prompt
    assert "Store all clearly durable memories from the turn, but only one per round." in prompt
    assert "Do not update topics in this node." in prompt
    assert "Fake tool JSON is invalid." in prompt
    assert "If you intend to perform an action, call the real tool." in prompt
    assert "If memory review is complete, reply exactly `DONE`." in prompt
    assert "Not allowed:" in prompt


def test_runtime_primary_agent_prompt_teaches_internal_classification() -> None:
    prompt = Path("resources/prompts/runtime_primary_agent.txt").read_text(encoding="utf-8")
    assert "Allowed internal task classes:" in prompt
    assert "`direct_answer`" in prompt
    assert "`retrieval_needed`" in prompt
    assert "`action_needed`" in prompt
    assert "`multi_step_plan`" in prompt
    assert "Keep classification and planning internal unless the user explicitly asks to see a plan." in prompt
