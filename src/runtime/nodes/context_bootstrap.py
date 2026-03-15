from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.nodes_common import (
    append_node_trace,
    get_emitter,
    message_to_state_payload,
    run_tools_mechanically,
)
from runtime.providers.types import Message, ToolCall
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

NODE_ID = "context.bootstrap"
GROUP = "context"
LABEL = "Context Bootstrap"
ROLE_KEY = ""


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _configured_chat_history_limit(resources) -> int:
    raw = getattr(resources, "prefill_chat_history_limit", 4)
    try:
        value = int(raw)
    except Exception:
        value = 4
    return max(0, value)


def _configured_socket_k(resources, attr_name: str, default: int) -> int:
    raw = getattr(resources, attr_name, default)
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(0, value)


def _world_identity_value(world: dict[str, Any], key: str) -> str:
    identity = world.get("identity")
    if not isinstance(identity, dict):
        return ""
    value = identity.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _build_prefill_calls(*, state: State, resources) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    world = state.get("world", {})
    if not isinstance(world, dict):
        world = {}

    query = _topic_query_from_world(world)
    if not query:
        return calls

    sockets = [
        ("shared", "shared", _configured_socket_k(resources, "prefill_shared_memory_k", 2)),
        ("user", _world_identity_value(world, "user_name"), _configured_socket_k(resources, "prefill_user_memory_k", 2)),
        ("agent", _world_identity_value(world, "agent_name"), _configured_socket_k(resources, "prefill_agent_memory_k", 2)),
    ]

    for socket_name, user_id, k in sockets:
        if k <= 0:
            continue
        if socket_name in {"user", "agent"} and not user_id:
            continue
        args = {"query": query, "k": k, "user_id": user_id}
        calls.append(("openmemory_query", args))

    chat_limit = _configured_chat_history_limit(resources)
    if chat_limit > 0:
        calls.append(("chat_history_tail", {"limit": chat_limit}))

    return calls


def _topic_query_from_world(world: dict[str, Any]) -> str:
    topics = world.get("topics")
    if not isinstance(topics, list):
        topics = []

    parts: list[str] = []

    project = world.get("project")
    if isinstance(project, str) and project.strip():
        parts.append(project.strip())

    for topic in topics[:8]:
        if isinstance(topic, str) and topic.strip():
            parts.append(topic.strip())

    return " | ".join(parts).strip()


def _is_synthetic_history_dump_message(record: dict[str, Any]) -> bool:
    role = str(record.get("role") or "").strip().lower()
    if role not in {"assistant", "you"}:
        return False

    content = record.get("content")
    if not isinstance(content, str):
        return False
    text = content.strip().lower()
    if len(text) < 80:
        return False

    has_turn_dump_intro = (
        ("chat turns" in text and "here are the last" in text)
        or ("most recent chat turns" in text)
    )
    has_serialized_turns = ('{"content":' in content or '"role":' in content)
    return has_turn_dump_intro and has_serialized_turns


def _message_role_from_chat_role(role: str) -> str:
    role_norm = str(role or "").strip().lower()
    if role_norm in {"human", "user"}:
        return "user"
    if role_norm in {"you", "assistant"}:
        return "assistant"
    return "user"


def _chat_history_messages(payload: Any) -> list[Message]:
    if not isinstance(payload, dict):
        return []

    records = payload.get("records")
    if not isinstance(records, list):
        return []

    out: list[Message] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if _is_synthetic_history_dump_message(rec):
            continue
        content = rec.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append(
            Message(
                role=_message_role_from_chat_role(str(rec.get("role") or "")),
                content=content,
            )
        )
    return out


def _strip_current_user_turn_from_history(
    messages: list[Message],
    *,
    current_user_text: str,
) -> list[Message]:
    if not messages:
        return messages

    current_text = str(current_user_text or "").strip()
    if not current_text:
        return messages

    last = messages[-1]
    if last.role != "user":
        return messages
    if last.tool_calls or last.name is not None or last.tool_call_id is not None:
        return messages
    if str(last.content or "").strip() != current_text:
        return messages
    return messages[:-1]


def _prefill_tool_messages(
    *,
    idx: int,
    tool_name: str,
    args: dict[str, Any],
    result_obj: Any,
) -> list[Message]:
    tool_call_id = f"bootstrap_prefill_{idx}"
    return [
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id=tool_call_id, name=tool_name, arguments_json=json.dumps(args, ensure_ascii=False, sort_keys=True))],
        ),
        Message(
            role="tool",
            name=tool_name,
            tool_call_id=tool_call_id,
            content=json.dumps(result_obj, ensure_ascii=False, sort_keys=True),
        ),
    ]


def _emit_skip_log(*, state: State, socket_name: str, reason: str) -> None:
    emitter = (state.get("runtime") or {}).get("emitter")
    if emitter is None:
        return
    emitter.emit(
        emitter.factory.log_line(
            level="info",
            logger="context_bootstrap",
            message=f"[bootstrap] skip {socket_name} memory prefill: {reason}",
            node_id=NODE_ID,
            span_id=None,
            fields={"socket": socket_name, "reason": reason},
        )
    )


def _log_skipped_memory_calls(*, state: State, resources) -> None:
    world = state.get("world", {})
    if not isinstance(world, dict):
        world = {}

    query = _topic_query_from_world(world)
    if not query:
        return

    sockets = [
        ("shared", "shared", _configured_socket_k(resources, "prefill_shared_memory_k", 2), None),
        ("user", _world_identity_value(world, "user_name"), _configured_socket_k(resources, "prefill_user_memory_k", 2), "current user identity missing"),
        ("agent", _world_identity_value(world, "agent_name"), _configured_socket_k(resources, "prefill_agent_memory_k", 2), "current agent identity missing"),
    ]
    for socket_name, user_id, k, missing_reason in sockets:
        if k <= 0:
            _emit_skip_log(state=state, socket_name=socket_name, reason="socket disabled (k=0)")
            continue
        if socket_name in {"user", "agent"} and not user_id:
            _emit_skip_log(state=state, socket_name=socket_name, reason=str(missing_reason or "identity missing"))


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def node(state: State) -> State:
        append_node_trace(state, NODE_ID)

        emitter = get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            rt = state.setdefault("runtime", {})
            if not isinstance(rt, dict):
                rt = {}
                state["runtime"] = rt

            _log_skipped_memory_calls(state=state, resources=services.tool_resources)

            toolset = services.tools.toolset_for_node("context_bootstrap")
            calls = _build_prefill_calls(state=state, resources=services.tool_resources)
            tool_msgs = run_tools_mechanically(
                toolset=toolset,
                calls=calls,
                emitter=emitter,
                node_id=NODE_ID,
                span_id=getattr(span, "span_id", None),
            )

            bootstrap_messages: list[dict[str, Any]] = []
            prefill_entries: list[dict[str, Any]] = []
            current_user_text = str((state.get("task") or {}).get("user_text") or "").strip()

            for idx, ((tool_name, args), msg) in enumerate(zip(calls, tool_msgs), start=1):
                result_obj = _safe_json_loads(msg.content or "")
                if tool_name == "chat_history_tail":
                    history_messages = _strip_current_user_turn_from_history(
                        _chat_history_messages(result_obj),
                        current_user_text=current_user_text,
                    )
                    for transcript_msg in history_messages:
                        bootstrap_messages.append(message_to_state_payload(transcript_msg))
                    continue

                if tool_name != "openmemory_query":
                    continue

                for transcript_msg in _prefill_tool_messages(
                    idx=idx,
                    tool_name=tool_name,
                    args=args,
                    result_obj=result_obj,
                ):
                    bootstrap_messages.append(message_to_state_payload(transcript_msg))

                prefill_entries.append(
                    {
                        "tool_name": tool_name,
                        "args": args,
                        "result": result_obj,
                    }
                )

            rt["context_bootstrap_status"] = "ok"
            rt["context_bootstrap_seeded"] = True
            rt["bootstrap_messages"] = bootstrap_messages
            rt["bootstrap_prefill_entries"] = prefill_entries

            span.end_ok()
            return state

        except Exception as e:
            span.end_error(code="NODE_ERROR", message=str(e))
            raise

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role=ROLE_KEY,
        make=make,
        prompt_name=None,
    )
)
