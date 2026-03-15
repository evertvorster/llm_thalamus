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

def test_runtime_reflect_prompt_teaches_reflect_complete_as_normal_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect.txt").read_text(encoding="utf-8")
    assert "`reflect_complete` is the normal successful completion action of this node" in prompt
    assert "If no clearly necessary maintenance exists, call `reflect_complete`." in prompt
    assert "If maintenance is complete, `reflect_complete` is the correct next action." in prompt
    assert "<<CONTEXT_JSON>>" not in prompt
    assert "always include `content`" in prompt
    assert "always include `user_id`" in prompt
    assert "compact retrieval index for future bootstrap memory recall" in prompt
    assert "if `WORLD.topics` is empty and clear enduring topics are visible, update it" in prompt
    assert "do not leave `WORLD.topics` empty when the conversation clearly contains durable recurring topics" in prompt
    assert "Fake tool JSON is invalid." in prompt
    assert "If you intend to finish, call the real `reflect_complete` tool." in prompt
    assert "You are not the conversational assistant for this turn." in prompt
    assert "Your task is maintenance, not conversation." in prompt
    assert "Use each input for its intended purpose:" in prompt
    assert "when the latest user turn is low-information, use recency and existing WORLD/TOPICS to keep the topic index stable" in prompt
    assert "Not allowed:" in prompt


def test_runtime_primary_agent_prompt_teaches_internal_classification() -> None:
    prompt = Path("resources/prompts/runtime_primary_agent.txt").read_text(encoding="utf-8")
    assert "Allowed internal task classes:" in prompt
    assert "`direct_answer`" in prompt
    assert "`retrieval_needed`" in prompt
    assert "`action_needed`" in prompt
    assert "`multi_step_plan`" in prompt
    assert "Keep classification and planning internal unless the user explicitly asks to see a plan." in prompt
