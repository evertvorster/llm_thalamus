from __future__ import annotations

import json

from runtime.nodes.context_bootstrap import _build_prefill_calls
from runtime.nodes.llm_primary_agent import (
    _build_primary_agent_messages,
    _classify_task,
    _sync_primary_execution_state,
    _transcript_is_ready,
)
from runtime.event_bus import EventBus
from runtime.events import TurnEventFactory
from runtime.emitter import TurnEmitter
from runtime.nodes_common import render_execution_state, run_controller_node
from runtime.providers.base import LLMProvider
from runtime.providers.types import (
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    Message,
    StreamEvent,
    ToolCall,
)
from runtime.tool_loop import ToolSet, chat_stream
from runtime.tools.resources import ToolResources


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubBuilder:
    def render_prompt(self, prompt_name: str) -> str:
        assert prompt_name == "runtime_primary_agent"
        return "SYSTEM CONTRACT\nWORLD\n{\"identity\":{}}\nSTATUS\nok\nEXECUTION STATE\n{}"


class _StreamingProvider(LLMProvider):
    def __init__(self, events: list[StreamEvent]):
        self._events = list(events)
        self.requests: list[ChatRequest] = []

    def provider_name(self) -> str:
        return "stub"

    def list_models(self) -> list[ModelInfo]:
        return []

    def chat_stream(self, req: ChatRequest):
        self.requests.append(req)
        yield from self._events

    def chat(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError


class _StubDeps:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def get_llm(self, role: str):
        _ = role
        return type("LLM", (), {"model": "stub", "params": {}})()

    def load_prompt(self, name: str) -> str:
        assert name == "runtime_primary_agent"
        return "PROMPT\n<<USER_MESSAGE>>\n<<EXECUTION_STATE>>"


class _StubServices:
    def __init__(self, toolset: ToolSet):
        self.tools = type(
            "Toolkit",
            (),
            {"toolset_for_node": lambda self, node_key: toolset},
        )()


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


def test_tool_enabled_final_response_preserves_streaming_text_deltas() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="Hello"),
            StreamEvent(type="delta_text", text=" world"),
            StreamEvent(type="done"),
        ]
    )

    events = list(
        chat_stream(
            provider=provider,
            model="stub",
            messages=[],
            params={},
            response_format=None,
            tools=ToolSet(defs=[], handlers={}),
            max_steps=1,
        )
    )

    assert [ev.text for ev in events if ev.type == "delta_text"] == ["Hello", " world"]
    assert events[-1].type == "done"


def test_tool_enabled_round_suppresses_text_when_a_tool_call_occurs() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="I should call a tool"),
            StreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="tc1",
                    name="demo_tool",
                    arguments_json=json.dumps({"value": 1}),
                ),
            ),
            StreamEvent(type="done"),
        ]
    )

    events = list(
        chat_stream(
            provider=provider,
            model="stub",
            messages=[],
            params={},
            response_format=None,
            tools=ToolSet(
                defs=[],
                handlers={"demo_tool": lambda args: {"ok": True, "echo": args["value"]}},
            ),
            max_steps=1,
            stop_after_tool_round=True,
        )
    )

    assert [ev.type for ev in events] == ["tool_call", "tool_result", "done"]


def test_completion_ready_controller_round_streams_without_tools() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="Hello"),
            StreamEvent(type="delta_text", text=" world"),
            StreamEvent(type="done"),
        ]
    )
    deps = _StubDeps(provider)
    services = _StubServices(ToolSet(defs=[], handlers={"demo_tool": lambda args: {"ok": True}}))

    bus = EventBus.create()
    emitter = TurnEmitter(TurnEventFactory(turn_id="test-turn"), bus.emit)
    state = {
        "task": {"user_text": "Say hello"},
        "runtime": {"emitter": emitter},
        "context": {},
        "final": {"answer": ""},
        "world": {},
    }

    def prepare_execution_state(state, execution):
        execution["completion_ready"] = True

    def on_final_text(state, final_text: str):
        state["final"]["answer"] = final_text

    run_controller_node(
        state=state,
        deps=deps,
        services=services,
        node_id="llm.primary_agent",
        label="Primary Agent",
        role_key="planner",
        prompt_name="runtime_primary_agent",
        node_key_for_tools="primary_agent",
        apply_tool_result=lambda state, tool_name, result_text: None,
        apply_handoff=lambda state, obj: False,
        max_rounds=1,
        prepare_execution_state=prepare_execution_state,
        allow_final_text=True,
        final_text_message_id="assistant:test",
        on_final_text=on_final_text,
    )

    events = []
    while True:
        ev = bus.poll(timeout_s=0.0)
        if ev is None:
            break
        events.append(ev)
    assistant_deltas = [
        str((ev.get("payload") or {}).get("text") or "")
        for ev in events
        if ev.get("type") == "assistant_delta"
    ]

    assert assistant_deltas == ["Hello", " world"]
    assert provider.requests
    assert provider.requests[0].tools is None
    assert state["final"]["answer"] == "Hello world"
