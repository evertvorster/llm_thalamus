from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.nodes_common.context import build_reflect_messages, recent_bootstrap_turns
from runtime.nodes_common.execution_state import ensure_planner_execution_state
from runtime.nodes_common.loop import run_reflect_node
from runtime.nodes_common.primitives import normalize_completion_sentinel, safe_json_loads
from runtime.nodes_common.tools import filter_toolset
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import ToolSet

NODE_ID = "llm.reflect_memory"
GROUP = "llm"
LABEL = "Reflect Memory"
PROMPT_NAME = "runtime_reflect_memory"
TASK_PROMPT_NAME = "runtime_reflect_memory_task"
ROLE_KEY = "reflect"
NODE_KEY_FOR_TOOLS = "reflect_memory"
MAX_ROUNDS = 10
RUNTIME_COMPLETE_KEY = "reflect_memory_complete"
RUNTIME_STATUS_KEY = "reflect_memory_status"
RUNTIME_RESULT_KEY = "reflect_memory_result"
RUNTIME_STORED_COUNT_KEY = "reflect_memory_stored_count"
NODE_STATUS_KEY = "reflect_memory"
PRIVATE_STORED_COUNT_KEY = "_reflect_memory_stored_count"
COMPLETION_CONDITION = "Reply DONE only when durable-memory review is complete."
COMPLETION_SENTINEL = "DONE"

def _recent_turns_evidence(state: State, *, limit: int = 10) -> list[dict[str, str]]:
    return recent_bootstrap_turns(state, limit=limit)


def _bootstrap_memory_evidence(state: State) -> list[dict[str, Any]]:
    rt = state.get("runtime") or {}
    raw = rt.get("bootstrap_prefill_entries") if isinstance(rt, dict) else None
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tool_name") or "").strip() != "openmemory_query":
            continue
        args = entry.get("args")
        if not isinstance(args, dict):
            args = {}
        out.append(
            {
                "tool_name": "openmemory_query",
                "socket_user_id": str(args.get("user_id") or "").strip(),
                "args": args,
                "result": entry.get("result"),
            }
        )
    return out


def _stored_memory_records(state: State) -> list[dict[str, Any]]:
    entries = (state.get("runtime") or {}).get("tool_transcripts")
    if not isinstance(entries, dict):
        return []
    raw = entries.get(NODE_ID)
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tool_name") or "").strip() != "openmemory_store":
            continue
        if not bool(entry.get("ok")):
            continue
        args = entry.get("args")
        if not isinstance(args, dict):
            args = {}
        out.append(
            {
                "content": str(args.get("content") or "").strip(),
                "user_id": str(args.get("user_id") or "").strip(),
                "type": str(args.get("type") or "contextual").strip() or "contextual",
            }
        )
    return out


def _prepare_reflect_evidence(state: State, services: RuntimeServices) -> None:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt
    _ = services
    rt["reflect_recent_turns"] = _recent_turns_evidence(state)
    rt["reflect_bootstrap_memory_evidence"] = _bootstrap_memory_evidence(state)


def _reflect_done(state: State) -> bool:
    rt = state.get("runtime", {})
    if not isinstance(rt, dict):
        return False
    return bool(rt.get(RUNTIME_COMPLETE_KEY, False))


def _stored_count(state: State) -> int:
    stored_count = state.get(PRIVATE_STORED_COUNT_KEY, 0)
    if not isinstance(stored_count, int):
        return 0
    return stored_count


def _allowed_memory_socket_ids(state: State) -> set[str]:
    world = state.get("world") or {}
    identity = world.get("identity") if isinstance(world, dict) else {}
    if not isinstance(identity, dict):
        identity = {}

    allowed = {"shared"}
    user_name = str(identity.get("user_name") or "").strip()
    agent_name = str(identity.get("agent_name") or "").strip()
    if user_name:
        allowed.add(user_name)
    if agent_name:
        allowed.add(agent_name)
    return allowed


def _memory_socket_guidance_text(state: State) -> str:
    world = state.get("world") or {}
    identity = world.get("identity") if isinstance(world, dict) else {}
    if not isinstance(identity, dict):
        identity = {}

    user_name = str(identity.get("user_name") or "").strip()
    agent_name = str(identity.get("agent_name") or "").strip()
    allowed = sorted(_allowed_memory_socket_ids(state))

    lines = [
        "MEMORY SOCKETS",
        "For this run, openmemory_store user_id must be exactly one of the following values.",
        "Do not invent IDs. Do not use UUIDs or placeholders.",
        "",
    ]
    if user_name:
        lines.append(f"- user socket: {user_name}")
    if agent_name:
        lines.append(f"- agent socket: {agent_name}")
    lines.append("- shared socket: shared")
    lines.extend(
        [
            "",
            "ALLOWED_USER_IDS_JSON:",
            json.dumps(allowed, ensure_ascii=False),
        ]
    )
    return "\n".join(lines)


def _build_plan_steps(state: State) -> list[dict[str, Any]]:
    complete = _reflect_done(state)
    return [
        {
            "id": "store_memory_if_needed",
            "tool": "openmemory_store",
            "purpose": "Store one clearly durable, reusable memory only if justified.",
            "status": "completed" if complete else "ready",
        },
        {
            "id": "complete_reflection_memory",
            "tool": COMPLETION_SENTINEL,
            "purpose": "Finish the memory-reflect node by replying DONE once durable-memory maintenance is complete.",
            "status": "completed" if complete else "ready",
        },
    ]


def _sync_execution_state(state: State) -> None:
    execution = ensure_planner_execution_state(state, NODE_ID)
    complete = _reflect_done(state)
    plan_steps = _build_plan_steps(state)
    execution["goal"] = "Perform required post-answer durable-memory extraction, dedupe, and storage."
    execution["mode"] = "planned"
    execution["completion_ready"] = complete
    execution["completion_ready_label"] = "DURABLE_MEMORY_COMPLETE"
    execution["missing_items_label"] = "UNRESOLVED_ITEMS_JSON"
    execution["artifact_label"] = "DURABLE_MEMORY"
    execution["terminal_action"] = COMPLETION_SENTINEL
    execution["completion_condition"] = COMPLETION_CONDITION
    execution["plan_steps"] = plan_steps
    execution["completed_steps"] = [
        str(step["id"]) for step in plan_steps if str(step.get("status")) == "completed"
    ]
    execution["current_step"] = "complete" if complete else "store_memory_if_needed"
    execution["missing_information"] = [] if complete else ["durable_memory_decision", "completion_decision"]
    execution["stored_count"] = _stored_count(state)
    execution["stored_this_turn"] = _stored_memory_records(state)


def _build_messages(state: State, builder) -> list[Message]:
    return build_reflect_messages(
        state=state,
        builder=builder,
        node_id=NODE_ID,
        role_key=ROLE_KEY,
        system_prompt_name=PROMPT_NAME,
        task_message=Message(
            role="user",
            content=builder.render_prompt(TASK_PROMPT_NAME).rstrip() + "\n\n" + _memory_socket_guidance_text(state),
        ),
        include_bootstrap_system_messages=True,
        include_recent_turns=False,
        recent_turn_limit=10,
        include_final_answer=True,
    )


def _toolset_for_round(state: State, default_toolset: ToolSet) -> ToolSet:
    allowed_user_ids = _allowed_memory_socket_ids(state)

    def _wrap_store(raw_store: Callable[..., Any]) -> Callable[..., Any]:
        def _guarded_store(args: dict[str, Any]) -> Any:
            user_id = str((args or {}).get("user_id") or "").strip()
            if not user_id:
                raise RuntimeError(
                    "openmemory_store requires user_id. Choose exactly one socket user_id from: "
                    + ", ".join(sorted(allowed_user_ids))
                )
            if user_id not in allowed_user_ids:
                raise RuntimeError(
                    "openmemory_store user_id must match one of the available memory sockets: "
                    + ", ".join(sorted(allowed_user_ids))
                )
            return raw_store(args)

        return _guarded_store

    return filter_toolset(
        default_toolset,
        allowed={"openmemory_store"},
        handler_wrappers={"openmemory_store": _wrap_store},
    )


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def _complete_memory(state: State, *, notes: str = "", issues: list[str] | None = None) -> None:
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt

        node_status = rt.setdefault("node_status", {})
        if not isinstance(node_status, dict):
            node_status = {}
            rt["node_status"] = node_status

        stored = _stored_memory_records(state)
        stored_count = len(stored)

        out_stored = list(stored)
        out_stored_count = int(stored_count)
        out_issues = [str(x).strip() for x in (issues or []) if str(x).strip()]
        out_notes = notes.strip()

        node_status[NODE_STATUS_KEY] = {
            "complete": True,
            "stored": out_stored,
            "stored_count": out_stored_count,
            "issues": out_issues,
            "notes": out_notes,
        }
        rt[RUNTIME_COMPLETE_KEY] = True
        rt[RUNTIME_STATUS_KEY] = "ok"
        rt[RUNTIME_STORED_COUNT_KEY] = out_stored_count
        rt[RUNTIME_RESULT_KEY] = {
            "complete": True,
            "stored": out_stored,
            "stored_count": out_stored_count,
            "issues": out_issues,
            "notes": out_notes,
        }
        state.pop(PRIVATE_STORED_COUNT_KEY, None)

    def _build_invalid_output_hint(error_message: str) -> str:
        err = str(error_message or "")
        if '"tool"' in err or "output must be a JSON object" in err or "model produced no final output" in err:
            return (
                "Do not explain. Do not emit fake tool JSON. "
                "If one more durable memory should be stored, call the real openmemory_store tool directly. "
                "Do not output objects with keys like tool, tool_name, args, or arguments. "
                "Choose exactly one memory socket and always include user_id. "
                "Use the minimal valid schema when possible: content string plus user_id string. "
                "type may only be contextual, factual, or both. "
                "facts must be an array if present. "
                f"If memory review is complete, reply exactly {COMPLETION_SENTINEL}."
            )
        return (
            "Do not explain. "
            "Use WORLD.topics, BOOTSTRAP MEMORY EVIDENCE, TOOL_TRANSCRIPT, and EXECUTION_STATE to determine the next memory action. "
            "Prioritize durable facts from the current user message over older retrieved memories. "
            "Choose one socket user_id from WORLD identity or shared, and include user_id on every openmemory_store call. "
            f"If memory review is complete, reply exactly {COMPLETION_SENTINEL}; otherwise call openmemory_store."
        )

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        payload = safe_json_loads(result_text)
        if payload is None:
            return

        if tool_name == "openmemory_store":
            if isinstance(payload, dict) and payload.get("ok"):
                state[PRIVATE_STORED_COUNT_KEY] = _stored_count(state) + 1
            return

    def _complete_on_sentinel(state: State) -> None:
        _complete_memory(state)

    def node(state: State) -> State:
        return run_reflect_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools=NODE_KEY_FOR_TOOLS,
            max_rounds=MAX_ROUNDS,
            completion_sentinel=COMPLETION_SENTINEL,
            stop_when=_reflect_done,
            prepare_evidence=lambda state: _prepare_reflect_evidence(state, services),
            prepare_execution_state=_sync_execution_state,
            build_task_message=lambda state, builder: Message(
                role="user",
                content=builder.render_prompt(TASK_PROMPT_NAME).rstrip() + "\n\n" + _memory_socket_guidance_text(state),
            ),
            toolset_for_round=_toolset_for_round,
            apply_tool_result=apply_tool_result,
            complete_on_sentinel=_complete_on_sentinel,
            build_invalid_output_hint=_build_invalid_output_hint,
            post_tool_guidance=(
                "Tool results above are evidence only. "
                f"If memory review is now complete, reply exactly {COMPLETION_SENTINEL}. "
                "If one more durable memory remains, call openmemory_store. "
                "Do not emit fake tool JSON."
            ),
        )

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role=ROLE_KEY,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
