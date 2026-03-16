from __future__ import annotations

import json

from runtime.nodes.context_bootstrap import (
    _build_prefill_calls,
    _chat_history_messages,
    _sanitize_openmemory_prefill_result,
    _strip_current_user_turn_from_history,
    _tool_environment_messages,
)
from runtime.nodes.llm_primary_agent import (
    _build_primary_agent_messages,
    _classify_task,
    make as make_primary_agent,
    _sync_primary_execution_state,
    _transcript_is_ready,
)
from runtime.event_bus import EventBus
from runtime.events import TurnEventFactory
from runtime.emitter import TurnEmitter
from runtime.nodes_common import append_tool_transcript_messages, render_execution_state, run_controller_node
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
from runtime.services import RuntimeServices
from runtime.tools.toolkit import RuntimeToolkit


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubBuilder:
    def render_prompt(self, prompt_name: str) -> str:
        if prompt_name == "runtime_primary_agent":
            return "PRIMARY AGENT SYSTEM"
        assert prompt_name == "runtime_primary_agent_task"
        return "PRIMARY AGENT TASK"


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
        assert name in {"runtime_primary_agent", "runtime_primary_agent_task"}
        return "PROMPT"


class _StubServices:
    def __init__(self, toolset: ToolSet):
        self.tools = type(
            "Toolkit",
            (),
            {"toolset_for_node": lambda self, node_key: toolset},
        )()


def test_context_bootstrap_prefill_uses_configured_limits() -> None:
    state = {"world": {"project": "Alpha", "topics": ["Planning"], "identity": {"user_name": "alice", "agent_name": "planner"}}}
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        prefill_chat_history_limit=9,
        prefill_shared_memory_k=3,
        prefill_user_memory_k=4,
        prefill_agent_memory_k=5,
    )

    calls = _build_prefill_calls(state=state, resources=resources)

    assert calls == [
        ("openmemory_query", {"query": "Alpha | Planning", "k": 3, "user_id": "shared"}),
        ("openmemory_query", {"query": "Alpha | Planning", "k": 4, "user_id": "alice"}),
        ("openmemory_query", {"query": "Alpha | Planning", "k": 5, "user_id": "planner"}),
        ("chat_history_tail", {"limit": 9}),
    ]


def test_context_bootstrap_includes_generic_tool_environment_init_message() -> None:
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        mcp_tool_catalog={
            "memory": [
                {
                    "name": "openmemory_query",
                    "description": "Query contextual memory",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "approval": "ask",
                }
            ]
        },
        internal_tool_policy={
            "world_apply_ops": {"approval": "auto"},
            "chat_history_tail": {"approval": "auto"},
        },
    )
    services = RuntimeServices(tools=RuntimeToolkit(resources=resources), tool_resources=resources)

    messages = _tool_environment_messages(services=services)

    assert len(messages) == 1
    assert messages[0].role == "system"
    assert messages[0].content.startswith("TOOL_ENVIRONMENT_INIT_JSON\n")
    payload = json.loads(messages[0].content.split("\n", 1)[1])
    assert payload["mcp_servers"][0]["server_id"] == "memory"
    assert payload["mcp_servers"][0]["tools"][0]["name"] == "openmemory_query"
    internal_names = {tool["name"] for tool in payload["internal_tools"]}
    assert {"chat_history_tail", "world_apply_ops"} <= internal_names


def test_chat_history_messages_filters_fake_tool_text_assistant_replies() -> None:
    payload = {
        "records": [
            {"role": "human", "content": "Please try mutating the world state directly."},
            {
                "role": "assistant",
                "content": "world_apply_ops\n{\n  \"ops\": [{\"op\": \"set\", \"path\": \"/project\", \"value\": \"llm_thalamus\"}]\n}",
            },
            {"role": "assistant", "content": "I can help with that once the tool succeeds."},
        ]
    }

    messages = _chat_history_messages(payload)

    assert [(m.role, m.content) for m in messages] == [
        ("user", "Please try mutating the world state directly."),
        ("assistant", "I can help with that once the tool succeeds."),
    ]


def test_primary_agent_transcript_shape_has_no_context_block_message() -> None:
    state = {
        "task": {"user_text": "What do you remember about my family?"},
        "runtime": {
            "bootstrap_messages": [
                {"role": "system", "content": "TOOL_ENVIRONMENT_INIT_JSON\n{\"internal_tools\":[]}"},
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "assistant", "content": "{\"ops\":[{\"op\":\"set\",\"path\":\"/project\",\"value\":\"marigold\"}]}"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "bootstrap_prefill_1",
                            "name": "openmemory_query",
                            "arguments_json": "{\"k\":10,\"query\":\"family\",\"user_id\":\"alice\"}",
                        }
                    ],
                },
                {
                    "role": "tool",
                    "name": "openmemory_query",
                    "tool_call_id": "bootstrap_prefill_1",
                    "content": "{\"ok\":true}",
                }
            ]
        },
    }

    messages = _build_primary_agent_messages(state, _StubBuilder())

    assert [m.role for m in messages] == ["system", "system", "system", "system", "system", "user", "assistant", "assistant", "assistant", "tool", "user"]
    assert "WORLD_STATE_JSON" in messages[0].content
    assert "NODE_CONTROL_STATE_JSON" in messages[1].content
    assert messages[2].content == "PRIMARY AGENT SYSTEM"
    assert "AVAILABLE TOOLS" in messages[3].content
    assert "TOOL_ENVIRONMENT_INIT_JSON" in str(messages[4].content or "")
    assert any(str(m.content or "").strip() == "{\"ops\":[{\"op\":\"set\",\"path\":\"/project\",\"value\":\"marigold\"}]}" for m in messages)
    assert messages[-1].content == "PRIMARY AGENT TASK"


def test_append_tool_transcript_messages_inserts_before_final_task_message() -> None:
    state = {
        "runtime": {
            "tool_transcripts": {
                "llm.primary_agent": [
                    {
                        "tool_call_id": "call_1",
                        "tool_name": "openmemory_query",
                        "args": {"query": "family", "k": 3},
                        "result_text": "{\"ok\":true,\"items\":[]}",
                        "ok": True,
                    }
                ]
            }
        }
    }
    base = [
        Message(role="system", content="WORLD"),
        Message(role="system", content="NODE"),
        Message(role="system", content="PRIMARY AGENT SYSTEM"),
        Message(role="user", content="PRIMARY AGENT TASK"),
    ]

    messages = append_tool_transcript_messages(base, state, "llm.primary_agent")

    assert [m.role for m in messages] == ["system", "system", "system", "assistant", "tool", "user"]
    assert messages[3].tool_calls is not None
    assert messages[3].tool_calls[0].name == "openmemory_query"
    assert messages[4].tool_call_id == "call_1"
    assert messages[4].content == "{\"ok\":true,\"items\":[]}"
    assert messages[5].content == "PRIMARY AGENT TASK"


def test_sanitize_openmemory_prefill_result_removes_json_only_output_memory() -> None:
    payload = {
        "content": [
            {"type": "text", "text": "Normal memory"},
            {"type": "text", "text": "User requires JSON-only output in llm_thalamus interactions."},
        ],
        "contextual": [
            {"id": "keep", "content": "Regular memory"},
            {"id": "drop", "content": "User explicitly requires JSON-only output with no additional text."},
        ],
        "text": "User explicitly requires JSON-only output with no additional text.",
        "raw": {
            "result": {
                "content": [
                    {"type": "text", "text": "Regular memory"},
                    {"type": "text", "text": "JSON-only output preference"},
                ],
                "contextual": [
                    {"id": "keep", "content": "Regular memory"},
                    {"id": "drop", "content": "JSON-only output preference"},
                ],
            }
        },
    }

    out = _sanitize_openmemory_prefill_result(payload)

    assert [item["id"] for item in out["contextual"]] == ["keep"]
    assert out["text"] == ""
    assert len(out["content"]) == 1
    assert [item["id"] for item in out["raw"]["result"]["contextual"]] == ["keep"]


def test_bootstrap_history_strips_trailing_current_user_turn_on_exact_match() -> None:
    history = [
        Message(role="user", content="Earlier question"),
        Message(role="assistant", content="Earlier answer"),
        Message(role="user", content="Current turn text"),
    ]

    out = _strip_current_user_turn_from_history(history, current_user_text="Current turn text")

    assert [m.content for m in out] == ["Earlier question", "Earlier answer"]


def test_bootstrap_history_keeps_trailing_user_turn_when_text_differs() -> None:
    history = [
        Message(role="user", content="Earlier question"),
        Message(role="assistant", content="Earlier answer"),
        Message(role="user", content="Different latest turn"),
    ]

    out = _strip_current_user_turn_from_history(history, current_user_text="Current turn text")

    assert [m.content for m in out] == [
        "Earlier question",
        "Earlier answer",
        "Different latest turn",
    ]


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


def test_primary_agent_classifies_world_mutation_requests_as_actions() -> None:
    state = {
        "task": {"user_text": "Interesting. Please try mutating the world state directly, and set the project to llm_thalamus"},
        "runtime": {},
        "world": {"project": None},
    }

    assert _classify_task(state) == "action_needed"


def test_primary_agent_classifies_retry_tool_call_requests_as_actions() -> None:
    state = {
        "task": {"user_text": "OK, please try that tool call again"},
        "runtime": {},
        "world": {"project": None},
    }

    assert _classify_task(state) == "action_needed"


def test_primary_agent_not_ready_for_retrieval_request_without_tool_evidence() -> None:
    state = {
        "task": {"user_text": "Show me the relevant memories about my family."},
        "runtime": {},
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "retrieval_needed"
    assert _transcript_is_ready(state) is False
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert "retrieval_evidence" in execution["missing_information"]


def test_primary_agent_action_request_not_ready_from_bootstrap_memory_evidence_alone() -> None:
    state = {
        "task": {"user_text": "Set project to llm_thalamus and set the goal to clean up the codebase."},
        "runtime": {
            "bootstrap_messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "bootstrap_prefill_1",
                            "name": "openmemory_query",
                            "arguments_json": "{\"query\":\"llm_thalamus\"}",
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
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "action_needed"
    assert _transcript_is_ready(state) is False
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert "action_result" in execution["missing_information"]
    assert execution["current_step"] == "take_next_tool_step"
    assert execution["completed_steps"] == []
    step_map = {str(step["id"]): str(step["status"]) for step in execution["plan_steps"]}
    assert step_map["take_next_tool_step"] == "pending"
    assert step_map["respond_to_user"] == "blocked"


def test_primary_agent_action_request_ready_after_action_tool_result() -> None:
    state = {
        "task": {"user_text": "Set project to llm_thalamus and set the goal to clean up the codebase."},
        "runtime": {
            "tool_transcripts": {
                "llm.primary_agent": [
                    {
                        "tool_name": "world_apply_ops",
                        "ok": True,
                    }
                ]
            }
        },
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "action_needed"
    assert _transcript_is_ready(state) is True
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert execution["current_step"] == "respond_to_user"


def test_primary_agent_completes_via_final_text() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="Final"),
            StreamEvent(type="delta_text", text=" reply"),
            StreamEvent(type="done"),
        ]
    )
    deps = _StubDeps(provider)
    resources = ToolResources(chat_history=_StubChatHistory())
    services = RuntimeServices(tools=RuntimeToolkit(resources=resources), tool_resources=resources)

    bus = EventBus.create()
    emitter = TurnEmitter(TurnEventFactory(turn_id="test-turn"), bus.emit)
    state = {
        "task": {"user_text": "Say hello"},
        "runtime": {
            "emitter": emitter,
            "turn_id": "test-turn",
            "bootstrap_messages": [{"role": "user", "content": "Hello there"}],
        },
        "final": {"answer": ""},
        "world": {"project": "llm_thalamus"},
    }

    node = make_primary_agent(deps, services)
    node(state)

    assert state["final"]["answer"] == "Final reply"
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert execution["response_emitted"] is True
    assert execution["current_step"] == "complete"

    events = []
    while True:
        ev = bus.poll(timeout_s=0.0)
        if ev is None:
            break
        events.append(ev)
    assert [ev.get("type") for ev in events if ev.get("type", "").startswith("assistant_")] == [
        "assistant_start",
        "assistant_delta",
        "assistant_delta",
        "assistant_end",
    ]


def test_primary_agent_explicit_plan_can_answer_without_tool_if_transcript_is_sufficient() -> None:
    state = {
        "task": {"user_text": "Make a plan to investigate the regression."},
        "runtime": {
            "bootstrap_messages": [
                {"role": "user", "content": "We need to investigate the regression."},
                {"role": "assistant", "content": "I can propose an implementation plan."},
            ]
        },
        "world": {"identity": {}},
    }

    _sync_primary_execution_state(state, {})

    assert _classify_task(state) == "multi_step_plan"
    assert _transcript_is_ready(state) is True
    execution = state["runtime"]["controller_execution"]["llm.primary_agent"]
    assert execution["completion_ready"] is True
    assert execution["current_step"] == "respond_to_user"


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


def test_primary_agent_can_allow_final_text_without_disabling_tools() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="Hello"),
            StreamEvent(type="done"),
        ]
    )
    deps = _StubDeps(provider)
    services = _StubServices(
        ToolSet(
            defs=[],
            handlers={"demo_tool": lambda args: {"ok": True}},
        )
    )

    bus = EventBus.create()
    emitter = TurnEmitter(TurnEventFactory(turn_id="test-turn"), bus.emit)
    state = {
        "task": {"user_text": "Say hello"},
        "runtime": {"emitter": emitter},
        "final": {"answer": ""},
        "world": {},
    }

    def prepare_execution_state(state, execution):
        execution["completion_ready"] = False

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
        require_completion_ready_for_final_text=False,
        disable_tools_when_final_text_allowed=False,
        final_text_message_id="assistant:test",
        on_final_text=lambda state, final_text: state["final"].update({"answer": final_text}),
    )

    assert provider.requests
    assert provider.requests[0].tools is not None


def test_primary_agent_rejects_final_text_before_completion_ready() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="world_apply_ops"),
            StreamEvent(type="done"),
        ]
    )
    deps = _StubDeps(provider)
    services = _StubServices(ToolSet(defs=[], handlers={"demo_tool": lambda args: {"ok": True}}))

    bus = EventBus.create()
    emitter = TurnEmitter(TurnEventFactory(turn_id="test-turn"), bus.emit)
    state = {
        "task": {"user_text": "Set the project"},
        "runtime": {"emitter": emitter},
        "final": {"answer": ""},
        "world": {},
    }

    def prepare_execution_state(state, execution):
        execution["completion_ready"] = False

    try:
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
            on_final_text=lambda state, final_text: state["final"].update({"answer": final_text}),
        )
    except RuntimeError as e:
        assert "final text is not allowed before completion_ready is true" in str(e)
    else:
        raise AssertionError("expected premature final text to be rejected")


def test_run_controller_node_can_preserve_prebuilt_system_messages() -> None:
    provider = _StreamingProvider(
        [
            StreamEvent(type="delta_text", text="Hello"),
            StreamEvent(type="done"),
        ]
    )
    deps = _StubDeps(provider)
    services = _StubServices(ToolSet(defs=[], handlers={}))

    bus = EventBus.create()
    emitter = TurnEmitter(TurnEventFactory(turn_id="test-turn"), bus.emit)
    state = {
        "task": {"user_text": "Say hello"},
        "runtime": {"emitter": emitter},
        "final": {"answer": ""},
        "world": {},
    }

    def prepare_execution_state(state, execution):
        execution["completion_ready"] = True

    def build_initial_messages(state, builder):
        return [
            Message(role="system", content="WORLD_STATE_JSON\n{}"),
            Message(role="system", content="NODE_CONTROL_STATE_JSON\n{}"),
            Message(role="user", content="Say hello"),
        ]

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
        build_initial_messages=build_initial_messages,
        replace_initial_system_message=False,
        allow_final_text=True,
        final_text_message_id="assistant:test",
        on_final_text=lambda state, final_text: state["final"].update({"answer": final_text}),
    )

    assert provider.requests
    sent = provider.requests[0].messages
    assert sent[0].content == "WORLD_STATE_JSON\n{}"
    assert sent[1].content == "NODE_CONTROL_STATE_JSON\n{}"
