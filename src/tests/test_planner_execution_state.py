from __future__ import annotations

from runtime.nodes.llm_reflect_memory import (
    NODE_ID as REFLECT_MEMORY_NODE_ID,
    _build_messages as _build_reflect_memory_messages,
    _memory_socket_guidance_text as _reflect_memory_socket_guidance_text,
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


def test_reflect_memory_socket_guidance_text_uses_world_identity_values() -> None:
    content = _reflect_memory_socket_guidance_text(
        {"world": {"identity": {"user_name": "alice", "agent_name": "planner"}}}
    )

    assert "MEMORY SOCKETS" in content
    assert "alice" in content
    assert "planner" in content
    assert "shared" in content
    assert '["alice", "planner", "shared"]' in content


def test_reflect_topics_initial_messages_include_shared_bootstrap_transcript() -> None:
    class _StubBuilder:
        def render_prompt(self, prompt_name: str) -> str:
            assert prompt_name in {"runtime_reflect_topics", "runtime_reflect_topics_task"}
            return "REFLECT TOPICS SYSTEM" if prompt_name == "runtime_reflect_topics" else "REFLECT TOPICS TASK"

    state = {
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "Earlier user"},
                {"role": "assistant", "content": "Earlier assistant"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "bootstrap_prefill_1",
                            "name": "openmemory_query",
                            "arguments_json": "{\"query\":\"family\"}",
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "openmemory_query",
                    "tool_call_id": "bootstrap_prefill_1",
                    "content": "{\"ok\":true}",
                },
            ]
        },
        "final": {"answer": "Final assistant answer"},
    }

    messages = _build_reflect_topics_messages(state, _StubBuilder())

    assert [msg.role for msg in messages] == ["system", "system", "system", "system", "user", "assistant", "assistant", "user"]
    assert "WORLD_STATE_JSON" in messages[0].content
    assert "NODE_CONTROL_STATE_JSON" in messages[1].content
    assert messages[2] == Message(role="system", content="REFLECT TOPICS SYSTEM")
    assert "AVAILABLE TOOLS" in messages[3].content
    assert messages[4] == Message(role="user", content="Earlier user")
    assert messages[5] == Message(role="assistant", content="Earlier assistant")
    assert all(msg.role != "tool" for msg in messages)
    assert all(not msg.tool_calls for msg in messages)
    assert messages[-2] == Message(role="assistant", content="Final assistant answer")
    assert messages[-1] == Message(role="user", content="REFLECT TOPICS TASK")


def test_reflect_memory_initial_messages_include_shared_bootstrap_transcript() -> None:
    class _StubBuilder:
        def render_prompt(self, prompt_name: str) -> str:
            assert prompt_name in {"runtime_reflect_memory", "runtime_reflect_memory_task"}
            return "REFLECT MEMORY SYSTEM" if prompt_name == "runtime_reflect_memory" else "REFLECT MEMORY TASK"

    state = {
        "world": {"identity": {"user_name": "alice", "agent_name": "planner"}},
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "Earlier user"},
                {"role": "assistant", "content": "Earlier assistant"},
            ]
        },
        "final": {"answer": "Final assistant answer"},
    }

    messages = _build_reflect_memory_messages(state, _StubBuilder())

    assert [msg.role for msg in messages] == ["system", "system", "system", "system", "user", "assistant", "assistant", "user"]
    assert "WORLD_STATE_JSON" in messages[0].content
    assert "NODE_CONTROL_STATE_JSON" in messages[1].content
    assert messages[2] == Message(role="system", content="REFLECT MEMORY SYSTEM")
    assert "AVAILABLE TOOLS" in messages[3].content
    assert messages[4] == Message(role="user", content="Earlier user")
    assert messages[5] == Message(role="assistant", content="Earlier assistant")
    assert messages[6] == Message(role="assistant", content="Final assistant answer")
    assert "REFLECT MEMORY TASK" in messages[7].content
    assert "MEMORY SOCKETS" in messages[7].content
    assert "alice" in messages[7].content
    assert "planner" in messages[7].content
    assert "shared" in messages[7].content


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


def test_reflect_memory_toolset_requires_socket_user_id() -> None:
    calls: list[dict] = []

    def _store(args):
        calls.append(dict(args))
        return {"ok": True}

    toolset = ToolSet(
        defs=[],
        handlers={"openmemory_store": _store},
    )

    gated = _reflect_memory_toolset_for_round(
        {"world": {"identity": {"user_name": "alice", "agent_name": "planner"}}},
        toolset,
    )

    try:
        gated.handlers["openmemory_store"]({"content": "x"})
    except RuntimeError as e:
        assert "requires user_id" in str(e)
    else:
        raise AssertionError("expected missing user_id to be rejected")

    result = gated.handlers["openmemory_store"]({"content": "x", "user_id": "alice"})
    assert result == {"ok": True}
    assert calls == [{"content": "x", "user_id": "alice"}]
