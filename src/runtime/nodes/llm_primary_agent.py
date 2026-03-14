from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    as_records,
    build_invalid_output_feedback_payload,
    ensure_planner_execution_state,
    replace_source_by_kind,
    run_controller_node,
)

NODE_ID = "llm.primary_agent"
GROUP = "llm"
LABEL = "Primary Agent"
PROMPT_NAME = "runtime_primary_agent"
ROLE_KEY = "planner"
MAX_CONTEXT_ROUNDS = 10
PRIMARY_COMPLETION_CONDITION = "Answer the user directly once CONTEXT is sufficient for a good response."
PRIMARY_STEP_DESCRIPTIONS = {
    "inspect_chat_history": ("chat_history_tail", "Load recent chat turns into CONTEXT."),
    "retrieve_memories": ("openmemory_query", "Retrieve durable memory candidates relevant to the turn."),
    "update_context": ("context_apply_ops", "Write an answer-ready CONTEXT block and mark sufficiency."),
    "answer_user": ("final_response", "Respond to the user directly once CONTEXT is sufficient."),
}


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_memory_records(payload: Any) -> list[Any]:
    records: list[Any] = []
    if not isinstance(payload, dict):
        return records

    text = payload.get("text")
    raw = payload.get("raw")
    content = payload.get("content")

    if isinstance(text, str) and text.strip():
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                records = parsed
            elif parsed is not None:
                records = [parsed]
        except Exception:
            records = [{"text": text.strip()}]

    if not records and isinstance(raw, dict):
        result = raw.get("result")
        if isinstance(result, dict):
            if isinstance(result.get("memories"), list):
                records = result.get("memories") or []
            elif isinstance(result.get("results"), list):
                records = result.get("results") or []
            elif isinstance(result.get("data"), list):
                records = result.get("data") or []
            elif result:
                records = [result]
        elif raw:
            records = [raw]

    if not records and isinstance(content, list):
        text_blocks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_blocks.append(item["text"])
        if text_blocks:
            records = [{"text": "\n".join(text_blocks).strip()}]

    return records


def _context_dict(state: State) -> dict[str, Any]:
    ctx = state.setdefault("context", {})
    if not isinstance(ctx, dict):
        ctx = {}
        state["context"] = ctx
    return ctx


def _source_kinds(ctx: dict[str, Any]) -> set[str]:
    raw_sources = ctx.get("sources")
    if not isinstance(raw_sources, list):
        return set()
    out: set[str] = set()
    for src in raw_sources:
        if not isinstance(src, dict):
            continue
        kind = str(src.get("kind") or "").strip()
        if kind:
            out.add(kind)
    return out


def _context_is_sufficient(ctx: dict[str, Any]) -> bool:
    if bool(ctx.get("complete", False)):
        return True
    next_node = str(ctx.get("next") or "").strip().lower()
    return next_node in {"answer", "respond", "primary_agent"}


def _infer_missing_information(ctx: dict[str, Any]) -> list[str]:
    if _context_is_sufficient(ctx):
        return []

    missing: list[str] = []
    kinds = _source_kinds(ctx)
    if "chat_turns" not in kinds:
        missing.append("recent_chat_turns")
    if "memories" not in kinds:
        missing.append("relevant_memory_candidates")
    if "world_update" not in kinds and not ctx.get("sources"):
        missing.append("current_world_context")
    missing.append("answer_ready_context")
    deduped: list[str] = []
    for item in missing:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _planner_step_status(*, step_id: str, ctx: dict[str, Any], execution: dict[str, Any]) -> str:
    kinds = _source_kinds(ctx)
    last_action_name = str(execution.get("last_action_name") or "")
    last_action_status = str(execution.get("last_action_status") or "")

    if step_id == "inspect_chat_history":
        if "chat_turns" in kinds:
            return "completed"
    elif step_id == "retrieve_memories":
        if "memories" in kinds:
            return "completed"
    elif step_id == "update_context":
        if _context_is_sufficient(ctx):
            return "completed"
        if last_action_name == "context_apply_ops" and last_action_status == "ok":
            return "in_progress"
    elif step_id == "answer_user":
        if bool(execution.get("response_emitted", False)):
            return "completed"
        if _context_is_sufficient(ctx):
            return "ready"
        return "blocked"

    expected_tool_name, _purpose = PRIMARY_STEP_DESCRIPTIONS[step_id]
    if expected_tool_name == last_action_name and last_action_status == "error":
        return "blocked"
    return "pending"


def _build_plan_steps(ctx: dict[str, Any], execution: dict[str, Any]) -> list[dict[str, Any]]:
    kinds = _source_kinds(ctx)
    desired_step_ids: list[str] = []
    if "chat_turns" not in kinds:
        desired_step_ids.append("inspect_chat_history")
    if "memories" not in kinds:
        desired_step_ids.append("retrieve_memories")
    if not _context_is_sufficient(ctx):
        desired_step_ids.append("update_context")
    desired_step_ids.append("answer_user")

    steps: list[dict[str, Any]] = []
    for step_id in desired_step_ids:
        tool_name, purpose = PRIMARY_STEP_DESCRIPTIONS[step_id]
        steps.append(
            {
                "id": step_id,
                "tool": tool_name,
                "purpose": purpose,
                "status": _planner_step_status(step_id=step_id, ctx=ctx, execution=execution),
            }
        )
    return steps


def _sync_primary_execution_state(state: State, execution: dict[str, Any]) -> None:
    execution = ensure_planner_execution_state(state, NODE_ID)
    ctx = _context_dict(state)

    execution["goal"] = str((state.get("task") or {}).get("user_text") or "").strip()
    execution["context_sufficient"] = _context_is_sufficient(ctx)
    execution["completion_ready"] = execution["context_sufficient"]
    execution["completion_ready_label"] = "CONTEXT_SUFFICIENT"
    execution["missing_items_label"] = "MISSING_INFORMATION_JSON"
    execution["artifact_label"] = "CONTEXT"
    execution["terminal_action"] = "final_response"
    execution["missing_information"] = _infer_missing_information(ctx)
    execution["completion_condition"] = PRIMARY_COMPLETION_CONDITION

    plan_steps = _build_plan_steps(ctx, execution)
    execution["plan_steps"] = plan_steps
    execution["completed_steps"] = [
        str(step.get("id") or "")
        for step in plan_steps
        if str(step.get("status") or "") == "completed"
    ]

    pending_or_ready = [
        str(step.get("id") or "")
        for step in plan_steps
        if str(step.get("status") or "") in {"pending", "ready", "in_progress"}
    ]
    execution["current_step"] = pending_or_ready[0] if pending_or_ready else "complete"

    actionable_steps = [
        step for step in plan_steps
        if str(step.get("id") or "") != "answer_user"
        and str(step.get("status") or "") in {"pending", "ready", "in_progress"}
    ]
    prior_mode = str(execution.get("mode") or "direct").strip() or "direct"
    if len(actionable_steps) > 1 or prior_mode == "planned":
        execution["mode"] = "planned"
    else:
        execution["mode"] = "direct"


def _update_primary_progress_from_tool(
    state: State,
    execution: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    tool_name = str(entry.get("tool_name") or "").strip()
    step_map = {
        "chat_history_tail": "inspect_chat_history",
        "openmemory_query": "retrieve_memories",
        "context_apply_ops": "update_context",
    }
    step_id = step_map.get(tool_name)
    if not step_id:
        return

    ok = bool(entry.get("ok"))
    execution["current_step"] = step_id
    if ok and step_id not in execution.get("completed_steps", []):
        completed = execution.get("completed_steps")
        if not isinstance(completed, list):
            completed = []
        completed = [str(x) for x in completed if str(x).strip()]
        completed.append(step_id)
        execution["completed_steps"] = completed

    _sync_primary_execution_state(state, execution)


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def _build_invalid_output_feedback(
        state: State,
        last_tool: str | None,
        error_message: str,
    ) -> dict[str, Any]:
        _ = state
        _ = error_message
        return build_invalid_output_feedback_payload(
            allowed_actions=["tool_call", "final_response"],
            last_tool=last_tool,
            node_hint=(
                "Do not explain. Do not apologize. Do not summarize your control flow. "
                "If the current context is sufficient, answer the user directly now. "
                "Otherwise call exactly one tool now."
            ),
        )

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        payload = _safe_json_loads(result_text)
        if payload is None:
            return

        if tool_name == "chat_history_tail":
            entry = {
                "kind": "chat_turns",
                "title": "Recent chat turns",
                "records": as_records(payload.get("records") if isinstance(payload, dict) else payload),
            }
            replace_source_by_kind(ctx, kind="chat_turns", entry=entry)
            return

        if tool_name == "openmemory_query":
            entry = {
                "kind": "memories",
                "title": "Memory candidates",
                "records": _normalize_memory_records(payload),
            }
            replace_source_by_kind(ctx, kind="memories", entry=entry)
            return

        if tool_name == "context_apply_ops":
            if isinstance(payload, dict) and isinstance(payload.get("context"), dict):
                state["context"] = payload["context"]
            return

        if tool_name == "world_apply_ops":
            if isinstance(payload, dict) and isinstance(payload.get("world"), dict):
                state["world"] = payload["world"]
                try:
                    emitter = (state.get("runtime") or {}).get("emitter")
                    if emitter is not None:
                        emitter.world_update(
                            node_id=NODE_ID,
                            span_id=None,
                            world=state.get("world", {}) or {},
                        )
                except Exception:
                    pass

            entry = {
                "kind": "world_update",
                "title": "World update result",
                "records": as_records(payload),
            }
            replace_source_by_kind(ctx, kind="world_update", entry=entry)
            return

        entry = {
            "kind": "tool_result",
            "title": f"Tool result: {tool_name}",
            "records": as_records(payload),
        }
        replace_source_by_kind(ctx, kind="tool_result", entry=entry)

    def apply_handoff(state: State, obj: dict) -> bool:
        _ = state
        _ = obj
        raise RuntimeError("primary_agent must either call a tool or emit final user-facing prose")

    def on_final_text(state: State, final_text: str) -> None:
        state.setdefault("final", {})["answer"] = final_text
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt
        execution = ensure_planner_execution_state(state, NODE_ID)
        execution["response_emitted"] = True
        execution["current_step"] = "complete"
        rt["primary_agent_complete"] = True
        rt["primary_agent_status"] = "answered"

    def node(state: State) -> State:
        turn_id = str(state.get("runtime", {}).get("turn_id", "") or "")
        message_id = f"assistant:{turn_id}" if turn_id else "assistant"
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="primary_agent",
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            stop_when=None,
            invalid_output_retry_limit=2,
            build_invalid_output_feedback=_build_invalid_output_feedback,
            max_rounds=MAX_CONTEXT_ROUNDS,
            prepare_execution_state=_sync_primary_execution_state,
            on_tool_executed=_update_primary_progress_from_tool,
            allow_final_text=True,
            final_text_message_id=message_id,
            on_final_text=on_final_text,
        )

    return node


register(NodeSpec(
    node_id=NODE_ID,
    group=GROUP,
    label=LABEL,
    role=ROLE_KEY,
    make=make,
    prompt_name=PROMPT_NAME,
))
