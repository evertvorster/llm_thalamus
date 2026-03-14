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
        "Context:\n<<CONTEXT_JSON>>",
        {"CONTEXT_JSON": '{"text": "literal <<NODE_ID>> marker"}'},
    )
    assert result == 'Context:\n{"text": "literal <<NODE_ID>> marker"}'


def test_render_tokens_does_not_mutate_inserted_values_in_later_passes() -> None:
    result = render_tokens(
        "<<A>> <<B>>",
        {
            "A": "literal <<B>>",
            "B": "final",
        },
    )
    assert result == "literal <<B>> final"


def test_runtime_context_builder_prompt_teaches_route_as_normal_completion() -> None:
    prompt = Path("resources/prompts/runtime_context_builder.txt").read_text(encoding="utf-8")
    assert "`route_node` is the normal successful completion action of this node" in prompt
    assert "successful completion occurs only when `route_node` has actually been called" in prompt
    assert "Do not call `context_apply_ops` if CONTEXT is already sufficient." in prompt
    assert "Do not emit pseudo-tool JSON such as `{\"action\":\"route_node\"}`." in prompt
    assert "If CONTEXT is sufficient, the correct next action is the actual `route_node` tool call." in prompt
    assert "`context_apply_ops` expects the current `context` object plus an `ops` array." in prompt
    assert "Do not treat \"I retrieved useful information\" as equivalent to a context update." in prompt


def test_runtime_reflect_prompt_teaches_reflect_complete_as_normal_completion() -> None:
    prompt = Path("resources/prompts/runtime_reflect.txt").read_text(encoding="utf-8")
    assert "`reflect_complete` is the normal successful completion action of this node" in prompt
    assert "If no clearly necessary maintenance exists, call `reflect_complete`." in prompt
    assert "If maintenance is complete, `reflect_complete` is the correct next action." in prompt
