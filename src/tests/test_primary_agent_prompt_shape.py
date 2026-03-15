from __future__ import annotations

from runtime.nodes.context_bootstrap import _build_prefill_calls
from runtime.nodes.llm_primary_agent import (
    _build_primary_agent_messages,
    _classify_task,
    _sync_primary_execution_state,
    _transcript_is_ready,
)
from runtime.nodes_common import render_execution_state
from runtime.tools.resources import ToolResources


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubBuilder:
    def render_prompt(self, prompt_name: str) -> str:
        assert prompt_name == "runtime_primary_agent"
        return "SYSTEM CONTRACT\nWORLD\n{\"identity\":{}}\nSTATUS\nok\nEXECUTION STATE\n{}"


def test_context_bootstrap_prefill_uses_configured_limits() -> None:
    state = {"world": {"project": "Alpha", "topics": ["Planning"]}}
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        prefill_chat_history_limit=9,
        prefill_memory_k=13,
    )

    calls = _build_prefill_calls(state=state, resources=resources)

    assert calls == [
        ("chat_history_tail", {"limit": 9}),
        ("openmemory_query", {"query": "Alpha | Planning", "k": 13}),
    ]


def test_primary_agent_transcript_shape_has_no_context_block_message() -> None:
    state = {
        "task": {"user_text": "What do you remember about my family?"},
        "context": {
            "sources": [
                {
                    "kind": "chat_turns",
                    "records": [
                        {"role": "human", "content": "Earlier question"},
                        {"role": "you", "content": "Earlier answer"},
                    ],
                }
            ]
        },
        "runtime": {
            "context_bootstrap_prefill": [
                {
                    "tool_name": "openmemory_query",
                    "args": {"query": "family", "k": 10},
                    "result": {"ok": True, "content": [{"type": "text", "text": "memory result"}]},
                }
            ]
        },
    }

    messages = _build_primary_agent_messages(state, _StubBuilder())

    assert messages[0].role == "system"
    assert "WORLD" in messages[0].content
    assert "STATUS" in messages[0].content
    assert "CONTEXT" not in messages[0].content
    assert "context_apply_ops" not in messages[0].content
    assert "synthetic prefill" not in messages[0].content
    assert "simulated" not in messages[0].content.lower()
    assert [m.role for m in messages[1:]] == ["user", "assistant", "assistant", "tool", "user"]
    assert messages[-1].content == "What do you remember about my family?"


def test_primary_agent_execution_state_is_a_compact_working_snapshot() -> None:
    state = {
        "task": {"user_text": "Make a plan to investigate the issue and then update the rule."},
        "runtime": {
            "controller_execution": {
                "llm.primary_agent": {
                    "current_round": 3,
                    "mode": "planned",
                    "task_class": "multi_step_plan",
                    "completion_ready": False,
                    "current_step": "take_next_tool_step",
                    "last_action_name": "openmemory_query",
                    "last_action_kind": "tool_call",
                    "last_action_status": "ok",
                    "missing_information": ["planned_intermediate_work"],
                    "completed_steps": ["inspect_chat_history"],
                    "plan_steps": [{"id": "take_next_tool_step", "status": "ready"}],
                }
            }
        }
    }

    rendered = render_execution_state(state, "llm.primary_agent", role_key="planner")

    assert "PRIMARY WORKING STATE" in rendered
    assert "TASK_CLASS: multi_step_plan" in rendered
    assert "COMPLETION_READY: false" in rendered
    assert "CURRENT_ROUND: 3" in rendered
    assert "MODE: planned" in rendered
    assert "CURRENT_STEP: take_next_tool_step" in rendered
    assert "MISSING_INFORMATION_JSON" in rendered
    assert "COMPLETED_STEPS_JSON" in rendered
    assert "PLAN_STEPS_JSON" in rendered
    assert "planned_intermediate_work" in rendered


def test_primary_agent_classifies_explicit_plan_requests_as_multi_step() -> None:
    state = {"task": {"user_text": "Make a plan to investigate the regression and then fix it."}}

    assert _classify_task(state) == "multi_step_plan"


def test_primary_agent_not_ready_for_retrieval_request_without_tool_evidence() -> None:
    state = {
        "task": {"user_text": "Show me the relevant memories about my family."},
        "context": {},
        "runtime": {},
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "retrieval_needed"
    assert _transcript_is_ready(state) is False
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert "retrieval_evidence" in execution["missing_information"]


def test_primary_agent_explicit_plan_can_answer_without_tool_if_transcript_is_sufficient() -> None:
    state = {
        "task": {"user_text": "Make a plan to investigate the regression."},
        "context": {
            "sources": [
                {
                    "kind": "chat_turns",
                    "records": [
                        {"role": "human", "content": "We need to investigate the regression."},
                        {"role": "you", "content": "I can propose an implementation plan."},
                    ],
                }
            ]
        },
        "runtime": {},
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "multi_step_plan"
    assert _transcript_is_ready(state) is True
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert execution["completion_ready"] is True
    assert execution["current_step"] == "answer_user"
