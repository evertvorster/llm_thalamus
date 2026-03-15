from __future__ import annotations

from runtime.nodes.llm_reflect_memory import (
    NODE_ID as REFLECT_MEMORY_NODE_ID,
    _build_messages as _build_reflect_memory_messages,
    _sync_execution_state as _sync_reflect_memory_execution_state,
    _toolset_for_round as _reflect_memory_toolset_for_round,
)
from runtime.nodes.llm_reflect_topics import (
    NODE_ID as REFLECT_TOPICS_NODE_ID,
    _build_messages as _build_reflect_topics_messages,
    _sync_execution_state as _sync_reflect_topics_execution_state,
    _toolset_for_round as _reflect_topics_toolset_for_round,
)
from runtime.nodes_common import render_execution_state
from runtime.providers.types import Message
from runtime.tool_loop import ToolSet


def test_reflect_topics_uses_planner_family_execution_state() -> None:
    state = {
        "task": {"user_text": "Keep the project themes stable."},
        "runtime": {},
        "final": {"answer": "I will keep the project themes stable."},
        "world": {},
    }

    _sync_reflect_topics_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_TOPICS_NODE_ID]

    assert reflect_state["goal"] == "Perform required post-answer topic continuity maintenance and canonical topic updates."
    assert reflect_state["completion_ready"] is False
    assert reflect_state["completion_ready_label"] == "TOPIC_MAINTENANCE_COMPLETE"
    assert reflect_state["terminal_action"] == "DONE"
    assert [step["id"] for step in reflect_state["plan_steps"]] == [
        "update_topics_if_needed",
        "complete_reflection_topics",
    ]


def test_reflect_memory_uses_planner_family_execution_state() -> None:
    state = {
        "task": {"user_text": "Remember the durable workflow rule."},
        "runtime": {},
        "final": {"answer": "I will follow the workflow rule."},
        "world": {"topics": ["workflow discipline"]},
    }

    _sync_reflect_memory_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_MEMORY_NODE_ID]

    assert reflect_state["goal"] == "Perform required post-answer durable-memory extraction, dedupe, and storage."
    assert reflect_state["completion_ready"] is False
    assert reflect_state["completion_ready_label"] == "DURABLE_MEMORY_COMPLETE"
    assert reflect_state["terminal_action"] == "DONE"
    assert [step["id"] for step in reflect_state["plan_steps"]] == [
        "store_memory_if_needed",
        "complete_reflection_memory",
    ]


def test_reflect_topics_execution_state_marks_completion_after_done() -> None:
    state = {
        "task": {"user_text": "No maintenance needed."},
        "runtime": {"reflect_topics_complete": True},
        "final": {"answer": "Done."},
        "world": {},
    }

    _sync_reflect_topics_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_TOPICS_NODE_ID]

    assert reflect_state["completion_ready"] is True
    assert reflect_state["missing_information"] == []
    assert reflect_state["current_step"] == "complete"
    rendered = render_execution_state(state, REFLECT_TOPICS_NODE_ID, role_key="reflect")
    assert rendered.find("DONE") != -1


def test_reflect_memory_execution_state_marks_completion_after_done() -> None:
    state = {
        "task": {"user_text": "No durable memory needed."},
        "runtime": {"reflect_memory_complete": True},
        "final": {"answer": "Done."},
        "world": {},
    }

    _sync_reflect_memory_execution_state(state, {})
    reflect_state = state["runtime"]["controller_execution"][REFLECT_MEMORY_NODE_ID]

    assert reflect_state["completion_ready"] is True
    assert reflect_state["missing_information"] == []
    assert reflect_state["current_step"] == "complete"
    rendered = render_execution_state(state, REFLECT_MEMORY_NODE_ID, role_key="reflect")
    assert rendered.find("DONE") != -1


def test_reflect_topics_initial_messages_do_not_include_bootstrap_transcript() -> None:
    class _StubBuilder:
        def render_prompt(self, prompt_name: str) -> str:
            assert prompt_name == "runtime_reflect_topics"
            return "REFLECT TOPICS SYSTEM"

    state = {
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "Earlier user"},
                {"role": "assistant", "content": "Earlier assistant"},
            ]
        },
        "final": {"answer": "Final assistant answer"},
    }

    messages = _build_reflect_topics_messages(state, _StubBuilder())

    assert messages == [
        Message(role="system", content="REFLECT TOPICS SYSTEM"),
        Message(role="assistant", content="Final assistant answer"),
    ]


def test_reflect_memory_initial_messages_do_not_include_bootstrap_transcript() -> None:
    class _StubBuilder:
        def render_prompt(self, prompt_name: str) -> str:
            assert prompt_name == "runtime_reflect_memory"
            return "REFLECT MEMORY SYSTEM"

    state = {
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "Earlier user"},
                {"role": "assistant", "content": "Earlier assistant"},
            ]
        },
        "final": {"answer": "Final assistant answer"},
    }

    messages = _build_reflect_memory_messages(state, _StubBuilder())

    assert messages == [
        Message(role="system", content="REFLECT MEMORY SYSTEM"),
        Message(role="assistant", content="Final assistant answer"),
    ]


def test_reflect_topics_toolset_is_fixed_to_topic_tools() -> None:
    toolset = ToolSet(
        defs=[],
        handlers={
            "world_apply_ops": lambda args: {"ok": True},
            "openmemory_store": lambda args: {"ok": True},
        },
    )

    gated = _reflect_topics_toolset_for_round({}, toolset)

    assert set(gated.handlers.keys()) == {"world_apply_ops"}


def test_reflect_memory_toolset_is_fixed_to_memory_tools() -> None:
    toolset = ToolSet(
        defs=[],
        handlers={
            "world_apply_ops": lambda args: {"ok": True},
            "openmemory_store": lambda args: {"ok": True},
        },
    )

    gated = _reflect_memory_toolset_for_round({}, toolset)

    assert set(gated.handlers.keys()) == {"openmemory_store"}
