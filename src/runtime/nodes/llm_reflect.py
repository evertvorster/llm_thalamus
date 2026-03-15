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

NODE_ID = "llm.reflect"
GROUP = "llm"
LABEL = "Reflect"
PROMPT_NAME = "runtime_reflect"
ROLE_KEY = "reflect"
MAX_REFLECT_ROUNDS = 10
REFLECT_COMPLETION_CONDITION = "Call reflect_complete only when required post-answer maintenance is complete."
REFLECT_STEP_DESCRIPTIONS = {
    "update_topics_if_needed": ("world_apply_ops", "Update WORLD topics only if enduring topics clearly need correction."),
    "store_memory_if_needed": ("openmemory_store", "Store a clearly durable, reusable memory only if justified."),
    "complete_reflection": ("reflect_complete", "Finish the reflect node once maintenance is complete."),
}


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _reflect_needs_topic_review(state: State) -> bool:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        return True
    node_status = rt.get("node_status") or {}
    if not isinstance(node_status, dict):
        return True
    reflect_status = node_status.get("reflect") or {}
    if not isinstance(reflect_status, dict):
        return True
    if bool(rt.get("reflect_tool_complete", False)):
        return False
    return "topics" not in reflect_status


def _reflect_needs_memory_review(state: State) -> bool:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        return True
    if bool(rt.get("reflect_tool_complete", False)):
        return False
    node_status = rt.get("node_status") or {}
    if not isinstance(node_status, dict):
        return True
    reflect_status = node_status.get("reflect") or {}
    if not isinstance(reflect_status, dict):
        return True
    return "stored" not in reflect_status and "stored_count" not in reflect_status


def _build_reflect_plan_steps(state: State, execution: dict[str, Any]) -> list[dict[str, Any]]:
    reflect_complete = bool((state.get("runtime") or {}).get("reflect_tool_complete", False))
    topics_done = bool(execution.get("topics_reviewed", False))
    memory_done = bool(execution.get("memory_reviewed", False))

    steps: list[dict[str, Any]] = []

    topic_status = "completed" if topics_done else "ready"
    memory_status = "completed" if memory_done else "ready"
    if reflect_complete:
        topic_status = "completed"
        memory_status = "completed"

    steps.append(
        {
            "id": "update_topics_if_needed",
            "tool": REFLECT_STEP_DESCRIPTIONS["update_topics_if_needed"][0],
            "purpose": REFLECT_STEP_DESCRIPTIONS["update_topics_if_needed"][1],
            "status": topic_status,
        }
    )
    steps.append(
        {
            "id": "store_memory_if_needed",
            "tool": REFLECT_STEP_DESCRIPTIONS["store_memory_if_needed"][0],
            "purpose": REFLECT_STEP_DESCRIPTIONS["store_memory_if_needed"][1],
            "status": memory_status,
        }
    )
    steps.append(
        {
            "id": "complete_reflection",
            "tool": REFLECT_STEP_DESCRIPTIONS["complete_reflection"][0],
            "purpose": REFLECT_STEP_DESCRIPTIONS["complete_reflection"][1],
            "status": "completed" if reflect_complete else "ready",
        }
    )
    return steps


def _sync_reflect_execution_state(state: State, execution: dict[str, Any]) -> None:
    execution = ensure_planner_execution_state(state, NODE_ID)
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        rt = {}

    reflect_complete = bool(rt.get("reflect_tool_complete", False))
    stored_count = state.get("_reflect_stored_count", 0)
    if not isinstance(stored_count, int):
        stored_count = 0

    topics_reviewed = bool(execution.get("topics_reviewed", False))
    memory_reviewed = bool(execution.get("memory_reviewed", False))
    if reflect_complete:
        topics_reviewed = True
        memory_reviewed = True

    execution["goal"] = "Perform required post-answer topic maintenance and durable memory persistence."
    execution["completion_ready"] = reflect_complete
    execution["completion_ready_label"] = "MAINTENANCE_COMPLETE"
    execution["missing_items_label"] = "UNRESOLVED_ITEMS_JSON"
    execution["artifact_label"] = "WORLD_AND_DURABLE_MEMORY"
    execution["terminal_action"] = "reflect_complete"
    execution["completion_condition"] = REFLECT_COMPLETION_CONDITION
    execution["topics_reviewed"] = topics_reviewed
    execution["memory_reviewed"] = memory_reviewed
    execution["stored_count"] = stored_count

    unresolved_items: list[str] = []
    if not reflect_complete:
        if _reflect_needs_topic_review(state) and not topics_reviewed:
            unresolved_items.append("topic_maintenance_review")
        if _reflect_needs_memory_review(state) and not memory_reviewed:
            unresolved_items.append("durable_memory_review")
        unresolved_items.append("completion_decision")

    execution["missing_information"] = unresolved_items
    plan_steps = _build_reflect_plan_steps(state, execution)
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
        if str(step.get("id") or "") != "complete_reflection"
        and str(step.get("status") or "") in {"pending", "ready", "in_progress"}
    ]
    prior_mode = str(execution.get("mode") or "direct").strip() or "direct"
    if len(actionable_steps) > 1 or prior_mode == "planned":
        execution["mode"] = "planned"
    else:
        execution["mode"] = "direct"


def _update_reflect_progress_from_tool(
    state: State,
    execution: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    tool_name = str(entry.get("tool_name") or "").strip()
    ok = bool(entry.get("ok"))
    step_map = {
        "world_apply_ops": "update_topics_if_needed",
        "openmemory_store": "store_memory_if_needed",
        "reflect_complete": "complete_reflection",
    }
    step_id = step_map.get(tool_name)
    if not step_id:
        return

    execution["current_step"] = step_id
    if ok:
        if step_id == "update_topics_if_needed":
            execution["topics_reviewed"] = True
        elif step_id == "store_memory_if_needed":
            execution["memory_reviewed"] = True

    _sync_reflect_execution_state(state, execution)


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def _reflect_done(state: State) -> bool:
        rt = state.get("runtime", {})
        if not isinstance(rt, dict):
            return False
        return bool(rt.get("reflect_tool_complete", False))

    def _apply_reflect_complete_from_tool(state: State, payload: dict[str, Any]) -> None:
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt

        node_status = rt.setdefault("node_status", {})
        if not isinstance(node_status, dict):
            node_status = {}
            rt["node_status"] = node_status

        topics = payload.get("topics")
        stored = payload.get("stored")
        stored_count = payload.get("stored_count")
        issues = payload.get("issues")
        notes = payload.get("notes")

        out_topics = [str(x) for x in topics] if isinstance(topics, list) else []
        out_stored = list(stored) if isinstance(stored, list) else []
        out_stored_count = int(stored_count) if isinstance(stored_count, (int, float)) and not isinstance(stored_count, bool) else 0
        out_issues = [str(x) for x in issues] if isinstance(issues, list) else []
        out_notes = notes.strip() if isinstance(notes, str) else ""

        node_status["reflect"] = {
            "complete": True,
            "topics": out_topics,
            "stored": out_stored,
            "stored_count": out_stored_count,
            "issues": out_issues,
            "notes": out_notes,
        }

        rt["reflect_complete"] = True
        rt["reflect_status"] = "ok"
        rt["reflect_stored_count"] = out_stored_count
        rt["reflect_result"] = {
            "complete": True,
            "topics": out_topics,
            "stored": out_stored,
            "stored_count": out_stored_count,
            "issues": out_issues,
            "notes": out_notes,
        }
        rt["reflect_tool_complete"] = True
        state.pop("_reflect_stored_count", None)

    def _build_invalid_output_feedback(
        state: State,
        last_tool: str | None,
        error_message: str,
    ) -> dict[str, Any]:
        _ = state
        _ = error_message
        return build_invalid_output_feedback_payload(
            allowed_actions=["tool_call", "reflect_complete"],
            last_tool=last_tool,
            node_hint=(
                "Do not explain. Do not apologize. Do not summarize. "
                "If reflection is complete, call reflect_complete now. "
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
                "title": "Topic update result",
                "records": as_records(payload),
            }
            replace_source_by_kind(ctx, kind="world_update", entry=entry)
            return

        if tool_name == "openmemory_store":
            if isinstance(payload, dict) and payload.get("ok"):
                stored_count = state.get("_reflect_stored_count", 0)
                if not isinstance(stored_count, int):
                    stored_count = 0
                state["_reflect_stored_count"] = stored_count + 1
            return

        if tool_name == "reflect_complete":
            if isinstance(payload, dict) and payload.get("ok"):
                _apply_reflect_complete_from_tool(state, payload)
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
        raise RuntimeError("reflect must hand off via reflect_complete tool")

    def node(state: State) -> State:
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="reflect",
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            stop_when=_reflect_done,
            invalid_output_retry_limit=2,
            build_invalid_output_feedback=_build_invalid_output_feedback,
            max_rounds=MAX_REFLECT_ROUNDS,
            prepare_execution_state=_sync_reflect_execution_state,
            on_tool_executed=_update_reflect_progress_from_tool,
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
