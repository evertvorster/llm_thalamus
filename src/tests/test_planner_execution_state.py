from __future__ import annotations

from runtime.nodes.llm_reflect import NODE_ID as REFLECT_NODE_ID, _sync_reflect_execution_state
from runtime.nodes_common import render_execution_state


def test_reflect_uses_planner_family_execution_state() -> None:
    state = {
        "task": {"user_text": "Remember the durable workflow rule."},
        "runtime": {},
        "context": {},
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
        "context": {},
        "final": {"answer": "Done."},
        "world": {},
    }

    _sync_reflect_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_NODE_ID]

    assert reflect_state["completion_ready"] is True
    assert reflect_state["missing_information"] == []
    assert reflect_state["current_step"] == "complete"
    assert render_execution_state(state, REFLECT_NODE_ID, role_key="reflect").find("reflect_complete") != -1
