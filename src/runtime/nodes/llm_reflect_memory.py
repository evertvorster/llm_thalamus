from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.nodes_common import (
    build_invalid_output_feedback_payload,
    ensure_planner_execution_state,
    normalize_completion_sentinel,
    run_controller_node,
)
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import ToolSet

NODE_ID = "llm.reflect_memory"
GROUP = "llm"
LABEL = "Reflect Memory"
PROMPT_NAME = "runtime_reflect_memory"
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


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _recent_turns_evidence(state: State, *, limit: int = 10) -> list[dict[str, str]]:
    rt = state.get("runtime") or {}
    raw = rt.get("bootstrap_messages") if isinstance(rt, dict) else None
    if not isinstance(raw, list):
        return []

    out: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip()
        content = entry.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        if entry.get("tool_calls") or entry.get("tool_call_id") or entry.get("name"):
            continue
        out.append({"role": role, "content": content})
    return out[-max(1, int(limit)) :]


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


def _prepare_reflect_evidence(state: State) -> None:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt
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


def _sync_execution_state(state: State, execution: dict[str, Any]) -> None:
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
    system_message = Message(role="system", content=builder.render_prompt(PROMPT_NAME))
    assistant_answer = str((state.get("final") or {}).get("answer") or "").strip()
    if assistant_answer:
        return [system_message, Message(role="assistant", content=assistant_answer)]
    return [system_message]


def _toolset_for_round(state: State, default_toolset: ToolSet) -> ToolSet:
    _ = state
    allowed = {"openmemory_store"}
    defs = [tool_def for tool_def in default_toolset.defs if tool_def.name in allowed]
    handlers = {name: handler for name, handler in default_toolset.handlers.items() if name in allowed}
    validators = None
    if default_toolset.validators:
        validators = {name: validator for name, validator in default_toolset.validators.items() if name in allowed}
    descriptors = {name: descriptor for name, descriptor in default_toolset.descriptors.items() if name in allowed}
    return ToolSet(
        defs=defs,
        handlers=handlers,
        validators=validators or None,
        descriptors=descriptors,
        approval_requester=default_toolset.approval_requester,
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

    def _build_invalid_output_feedback(
        state: State,
        last_tool: str | None,
        error_message: str,
    ) -> dict[str, Any]:
        _ = state
        err = str(error_message or "")
        if '"tool"' in err or "output must be a JSON object" in err or "model produced no final output" in err:
            node_hint = (
                "Do not explain. Do not emit fake tool JSON. "
                "If one more durable memory should be stored, call openmemory_store. "
                f"If memory review is complete, reply exactly {COMPLETION_SENTINEL}."
            )
        else:
            node_hint = (
                "Do not explain. "
                "Use WORLD.topics, BOOTSTRAP MEMORY EVIDENCE, TOOL_TRANSCRIPT, and EXECUTION_STATE to determine the next memory action. "
                f"If memory review is complete, reply exactly {COMPLETION_SENTINEL}; otherwise call openmemory_store."
            )
        return build_invalid_output_feedback_payload(
            allowed_actions=["tool_call", COMPLETION_SENTINEL],
            last_tool=last_tool,
            node_hint=node_hint,
        )

    def _build_post_tool_result_messages(state: State, tool_name: str, result_text: str) -> list[Message]:
        _ = state
        _ = tool_name
        _ = result_text
        return [
            Message(
                role="system",
                content=(
                    "Tool results above are evidence only. "
                    f"If memory review is now complete, reply exactly {COMPLETION_SENTINEL}. "
                    "If one more durable memory remains, call openmemory_store. "
                    "Do not emit fake tool JSON."
                ),
            )
        ]

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        payload = _safe_json_loads(result_text)
        if payload is None:
            return

        if tool_name == "openmemory_store":
            if isinstance(payload, dict) and payload.get("ok"):
                state[PRIVATE_STORED_COUNT_KEY] = _stored_count(state) + 1
            return

    def on_completion_sentinel(state: State, sentinel: str) -> bool:
        if normalize_completion_sentinel(sentinel) != COMPLETION_SENTINEL:
            return False
        _complete_memory(state)
        return True

    def apply_handoff(state: State, obj: dict) -> bool:
        _ = state
        _ = obj
        raise RuntimeError("reflect_memory completes only by replying DONE")

    def node(state: State) -> State:
        _prepare_reflect_evidence(state)
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools=NODE_KEY_FOR_TOOLS,
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            stop_when=_reflect_done,
            invalid_output_retry_limit=2,
            build_invalid_output_feedback=_build_invalid_output_feedback,
            max_rounds=MAX_ROUNDS,
            prepare_execution_state=_sync_execution_state,
            build_initial_messages=_build_messages,
            toolset_for_round=_toolset_for_round,
            completion_sentinels=[COMPLETION_SENTINEL],
            on_completion_sentinel=on_completion_sentinel,
            build_post_tool_result_messages=_build_post_tool_result_messages,
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
