from __future__ import annotations

from runtime.nodes.llm_context_builder import NODE_ID, _sync_planner_execution_state
from runtime.nodes_common import render_execution_state
from runtime.tools.policy.node_skill_policy import NODE_ALLOWED_SKILLS


def test_context_builder_planner_state_tracks_missing_information() -> None:
    state = {
        "task": {"user_text": "Summarize what changed in the project."},
        "runtime": {},
        "context": {},
        "world": {},
    }
    execution = {}

    _sync_planner_execution_state(state, execution)

    planner_state = state["runtime"]["controller_execution"][NODE_ID]
    assert planner_state["goal"] == "Summarize what changed in the project."
    assert planner_state["context_sufficient"] is False
    assert planner_state["mode"] == "planned"
    assert planner_state["missing_information"] == [
        "recent_chat_turns",
        "relevant_memory_candidates",
        "current_world_context",
        "answer_ready_context",
    ]
    assert planner_state["current_step"] == "inspect_chat_history"
    assert [step["id"] for step in planner_state["plan_steps"]] == [
        "inspect_chat_history",
        "retrieve_memories",
        "update_context",
        "route_to_answer",
    ]


def test_context_builder_planner_state_routes_only_after_context_is_sufficient() -> None:
    state = {
        "task": {"user_text": "Answer with the latest project context."},
        "runtime": {},
        "context": {
            "complete": True,
            "next": "answer",
            "sources": [
                {"kind": "chat_turns", "records": []},
                {"kind": "memories", "records": []},
            ],
        },
        "world": {},
    }
    execution = {}

    _sync_planner_execution_state(state, execution)

    planner_state = state["runtime"]["controller_execution"][NODE_ID]
    assert planner_state["context_sufficient"] is True
    assert planner_state["missing_information"] == []
    assert planner_state["current_step"] == "route_to_answer"
    assert planner_state["plan_steps"] == [
        {
            "id": "route_to_answer",
            "tool": "route_node",
            "purpose": "Hand off to the Answer node once CONTEXT is sufficient.",
            "status": "ready",
        }
    ]


def test_render_execution_state_includes_planner_working_state() -> None:
    state = {
        "task": {"user_text": "Need enough context to answer."},
        "runtime": {},
        "context": {},
        "world": {},
    }

    _sync_planner_execution_state(state, {})
    rendered = render_execution_state(state, NODE_ID, role_key="planner")

    assert "PLANNER WORKING STATE" in rendered
    assert "PLAN_STEPS_JSON" in rendered
    assert "recent_chat_turns" in rendered


def test_context_builder_has_context_mutation_tool_access() -> None:
    assert "core_context_mutation" in NODE_ALLOWED_SKILLS["context_builder"]
