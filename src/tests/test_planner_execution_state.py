from __future__ import annotations

from runtime.nodes.llm_reflect import (
    NODE_ID as REFLECT_NODE_ID,
    _build_reflect_messages,
    _sync_reflect_execution_state,
)
from runtime.nodes_common import render_execution_state
from runtime.providers.types import Message


def test_reflect_uses_planner_family_execution_state() -> None:
    state = {
        "task": {"user_text": "Remember the durable workflow rule."},
        "runtime": {},
        "final": {"answer": "I will follow the workflow rule."},
        "world": {},
    }

    _sync_reflect_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_NODE_ID]

    assert reflect_state["goal"] == "Perform required post-answer topic maintenance and durable memory persistence."
    assert reflect_state["completion_ready"] is False
    assert reflect_state["completion_ready_label"] == "MAINTENANCE_COMPLETE"
    assert reflect_state["terminal_action"] == "reflect_complete"
    assert [step["id"] for step in reflect_state["plan_steps"]] == [
        "update_topics_if_needed",
        "store_memory_if_needed",
        "complete_reflection",
    ]


def test_reflect_execution_state_marks_completion_after_reflect_complete() -> None:
    state = {
        "task": {"user_text": "No maintenance needed."},
        "runtime": {"reflect_tool_complete": True},
        "final": {"answer": "Done."},
        "world": {},
    }

    _sync_reflect_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_NODE_ID]

    assert reflect_state["completion_ready"] is True
    assert reflect_state["missing_information"] == []
    assert reflect_state["current_step"] == "complete"
    rendered = render_execution_state(state, REFLECT_NODE_ID, role_key="reflect")
    assert rendered.find("reflect_complete") != -1
    assert "CONTEXT" not in rendered


def test_reflect_initial_messages_do_not_include_bootstrap_transcript() -> None:
    class _StubBuilder:
        def render_prompt(self, prompt_name: str) -> str:
            assert prompt_name == "runtime_reflect"
            return "REFLECT SYSTEM"

    state = {
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "Earlier user"},
                {"role": "assistant", "content": "Earlier assistant"},
            ]
        },
        "final": {"answer": "Final assistant answer"},
    }

    messages = _build_reflect_messages(state, _StubBuilder())

    assert messages == [
        Message(role="system", content="REFLECT SYSTEM"),
        Message(role="assistant", content="Final assistant answer"),
    ]
