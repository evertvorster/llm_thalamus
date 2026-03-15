from __future__ import annotations

import json
import re
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    build_invalid_output_feedback_payload,
    ensure_controller_execution_state,
    stable_json,
    ensure_tool_transcript,
    run_controller_node,
)
from runtime.providers.types import Message, ToolCall

NODE_ID = "llm.primary_agent"
GROUP = "llm"
LABEL = "Primary Agent"
PROMPT_NAME = "runtime_primary_agent"
ROLE_KEY = "planner"
MAX_CONTEXT_ROUNDS = 10
TASK_CLASS_DIRECT_ANSWER = "direct_answer"
TASK_CLASS_RETRIEVAL_NEEDED = "retrieval_needed"
TASK_CLASS_ACTION_NEEDED = "action_needed"
TASK_CLASS_MULTI_STEP_PLAN = "multi_step_plan"
PRIMARY_STEP_DESCRIPTIONS = {
    "inspect_chat_history": ("chat_history_tail", "Load recent chat turns if more visible conversation context is needed."),
    "take_next_tool_step": ("tool_call", "Use one retrieval or action tool if more evidence or work is needed."),
    "answer_user": ("final_response", "Respond to the user directly once WORLD, STATUS, and the transcript are sufficient."),
}


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _message_role_from_chat_role(role: str) -> str:
    role_norm = str(role or "").strip().lower()
    if role_norm in {"human", "user"}:
        return "user"
    if role_norm in {"you", "assistant"}:
        return "assistant"
    return "user"


def _recent_chat_messages(state: State) -> list[Message]:
    ctx = state.get("context") or {}
    if not isinstance(ctx, dict):
        return []

    sources = ctx.get("sources")
    if not isinstance(sources, list):
        return []

    for source in sources:
        if not isinstance(source, dict):
            continue
        if str(source.get("kind") or "").strip() != "chat_turns":
            continue
        records = source.get("records")
        if not isinstance(records, list):
            return []

        out: list[Message] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            role = _message_role_from_chat_role(str(rec.get("role") or ""))
            content = rec.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            out.append(Message(role=role, content=content))
        return out

    return []


def _synthetic_prefill_messages(state: State) -> list[Message]:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        return []

    raw = rt.get("context_bootstrap_prefill")
    if not isinstance(raw, list):
        return []

    messages: list[Message] = []
    for idx, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name") or "").strip()
        if not tool_name:
            continue
        args_obj = entry.get("args")
        result_obj = entry.get("result")
        tool_call_id = f"bootstrap_prefill_{idx}"
        args_json = stable_json(args_obj if isinstance(args_obj, dict) else {})
        result_json = stable_json(result_obj)

        messages.append(
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id=tool_call_id, name=tool_name, arguments_json=args_json)],
            )
        )
        messages.append(
            Message(
                role="tool",
                name=tool_name,
                tool_call_id=tool_call_id,
                content=result_json,
            )
        )

    return messages


def _build_primary_agent_messages(state: State, builder) -> list[Message]:
    system_message = Message(role="system", content=builder.render_prompt(PROMPT_NAME))
    chat_messages = _recent_chat_messages(state)
    prefill_messages = _synthetic_prefill_messages(state)
    user_text = str((state.get("task") or {}).get("user_text") or "").strip()
    current_user = Message(role="user", content=user_text)
    return [system_message, *chat_messages, *prefill_messages, current_user]


def _world_has_authoritative_content(state: State) -> bool:
    world = state.get("world")
    return isinstance(world, dict) and bool(world)


def _bootstrap_prefill_tool_names(state: State) -> set[str]:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        return set()

    raw = rt.get("context_bootstrap_prefill")
    if not isinstance(raw, list):
        return set()

    out: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name") or "").strip()
        if tool_name:
            out.add(tool_name)
    return out


def _tool_transcript_names(state: State) -> set[str]:
    entries = ensure_tool_transcript(state, NODE_ID)
    out: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name") or "").strip()
        if tool_name:
            out.add(tool_name)
    return out


def _current_user_text(state: State) -> str:
    return str((state.get("task") or {}).get("user_text") or "").strip()


def _has_tool_evidence(state: State) -> bool:
    return bool(_bootstrap_prefill_tool_names(state) | _tool_transcript_names(state))


def _is_explicit_plan_request(user_text: str) -> bool:
    text = user_text.lower()
    if not text:
        return False
    return any(
        phrase in text
        for phrase in (
            "make a plan",
            "give me a plan",
            "create a plan",
            "plan this",
            "implementation plan",
            "migration plan",
            "rollout plan",
            "step-by-step plan",
        )
    )


def _looks_like_multi_step_request(user_text: str) -> bool:
    text = user_text.lower()
    if not text:
        return False
    if _is_explicit_plan_request(user_text):
        return True
    if re.search(r"\b(first|then|after that|next|finally)\b", text):
        return True
    if re.search(r"\b(plan|steps|strategy|approach|investigate|debug|diagnose|compare)\b", text):
        return True
    return text.count(" and ") >= 2


def _looks_like_action_request(user_text: str) -> bool:
    text = user_text.lower()
    if not text:
        return False
    return any(
        phrase in text
        for phrase in (
            "set ",
            "unset ",
            "remove ",
            "delete ",
            "add ",
            "update ",
            "change ",
            "store ",
            "save ",
            "write ",
            "use world apply ops",
        )
    )


def _looks_like_retrieval_request(user_text: str) -> bool:
    text = user_text.lower()
    if not text:
        return False
    return any(
        phrase in text
        for phrase in (
            "what do you remember",
            "fetch ",
            "show me",
            "list ",
            "find ",
            "look up",
            "search ",
            "display ",
            "which memories",
            "what memories",
        )
    )


def _classify_task(state: State) -> str:
    user_text = _current_user_text(state)
    if _is_explicit_plan_request(user_text):
        return TASK_CLASS_MULTI_STEP_PLAN
    if _looks_like_multi_step_request(user_text):
        return TASK_CLASS_MULTI_STEP_PLAN
    if _looks_like_action_request(user_text):
        return TASK_CLASS_ACTION_NEEDED
    if _looks_like_retrieval_request(user_text):
        return TASK_CLASS_RETRIEVAL_NEEDED
    return TASK_CLASS_DIRECT_ANSWER


def _transcript_is_ready(state: State) -> bool:
    if bool((ensure_controller_execution_state(state, NODE_ID)).get("response_emitted", False)):
        return True

    task_class = _classify_task(state)
    has_recent_chat = bool(_recent_chat_messages(state))
    has_world = _world_has_authoritative_content(state)
    has_tool_evidence = _has_tool_evidence(state)

    if task_class == TASK_CLASS_DIRECT_ANSWER:
        return has_world and (has_recent_chat or has_tool_evidence)
    if task_class == TASK_CLASS_RETRIEVAL_NEEDED:
        return has_tool_evidence
    if task_class == TASK_CLASS_ACTION_NEEDED:
        return has_tool_evidence
    if task_class == TASK_CLASS_MULTI_STEP_PLAN:
        user_text = _current_user_text(state)
        if _is_explicit_plan_request(user_text):
            return has_world and (has_recent_chat or has_tool_evidence)
        return has_tool_evidence
    return has_world and (has_recent_chat or has_tool_evidence)


def _infer_missing_information(state: State) -> list[str]:
    task_class = _classify_task(state)
    if _transcript_is_ready(state):
        if task_class == TASK_CLASS_MULTI_STEP_PLAN:
            return ["plan_synthesis"] if not _has_tool_evidence(state) and not _recent_chat_messages(state) else []
        return []

    missing: list[str] = []
    if not _recent_chat_messages(state):
        missing.append("recent_chat_turns")
    if not _world_has_authoritative_content(state):
        missing.append("world_status_review")
    has_tool_evidence = _has_tool_evidence(state)
    if task_class in {TASK_CLASS_RETRIEVAL_NEEDED, TASK_CLASS_ACTION_NEEDED, TASK_CLASS_MULTI_STEP_PLAN} and not has_tool_evidence:
        if task_class == TASK_CLASS_RETRIEVAL_NEEDED:
            missing.append("retrieval_evidence")
        elif task_class == TASK_CLASS_ACTION_NEEDED:
            missing.append("action_result")
        else:
            missing.append("planned_intermediate_work")
    if task_class == TASK_CLASS_MULTI_STEP_PLAN and _is_explicit_plan_request(_current_user_text(state)):
        missing.append("plan_synthesis")
    deduped: list[str] = []
    for item in missing:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _planner_step_status(*, step_id: str, state: State, execution: dict[str, Any]) -> str:
    seen_tools = _bootstrap_prefill_tool_names(state) | _tool_transcript_names(state)
    last_action_name = str(execution.get("last_action_name") or "")
    last_action_status = str(execution.get("last_action_status") or "")

    if step_id == "inspect_chat_history":
        if _recent_chat_messages(state):
            return "completed"
    elif step_id == "take_next_tool_step":
        if any(name != "chat_history_tail" for name in seen_tools):
            return "completed"
        if last_action_name not in {"", "none"} and last_action_name != "chat_history_tail" and last_action_status == "ok":
            return "in_progress"
    elif step_id == "answer_user":
        if bool(execution.get("response_emitted", False)):
            return "completed"
        if _transcript_is_ready(state):
            return "ready"
        return "blocked"

    expected_tool_name, _purpose = PRIMARY_STEP_DESCRIPTIONS[step_id]
    if expected_tool_name != "tool_call" and expected_tool_name == last_action_name and last_action_status == "error":
        return "blocked"
    if expected_tool_name == "tool_call" and last_action_name not in {"", "none"} and last_action_status == "error":
        return "blocked"
    return "pending"


def _build_plan_steps(state: State, execution: dict[str, Any]) -> list[dict[str, Any]]:
    task_class = str(execution.get("task_class") or _classify_task(state))
    desired_step_ids: list[str] = []
    if not _recent_chat_messages(state):
        desired_step_ids.append("inspect_chat_history")
    needs_tool_step = (
        task_class in {TASK_CLASS_RETRIEVAL_NEEDED, TASK_CLASS_ACTION_NEEDED, TASK_CLASS_MULTI_STEP_PLAN}
        and not _has_tool_evidence(state)
        and not _transcript_is_ready(state)
    )
    if needs_tool_step:
        desired_step_ids.append("take_next_tool_step")
    desired_step_ids.append("answer_user")

    steps: list[dict[str, Any]] = []
    for step_id in desired_step_ids:
        tool_name, purpose = PRIMARY_STEP_DESCRIPTIONS[step_id]
        steps.append(
            {
                "id": step_id,
                "tool": tool_name,
                "purpose": purpose,
                "status": _planner_step_status(step_id=step_id, state=state, execution=execution),
            }
        )
    return steps


def _sync_primary_execution_state(state: State, execution: dict[str, Any]) -> None:
    execution = ensure_controller_execution_state(state, NODE_ID)
    task_class = _classify_task(state)
    missing_information = _infer_missing_information(state)
    execution["goal"] = _current_user_text(state)
    execution["task_class"] = task_class
    execution["completion_ready"] = _transcript_is_ready(state)
    execution["completion_ready_label"] = "COMPLETION_READY"
    execution["missing_items_label"] = "MISSING_INFORMATION_JSON"
    execution["artifact_label"] = "WORKING_TRANSCRIPT"
    execution["terminal_action"] = "final_response"
    execution["completion_condition"] = "Answer only when the work required by the current task class is complete."
    execution["missing_information"] = missing_information
    execution["mode"] = "planned" if task_class == TASK_CLASS_MULTI_STEP_PLAN else "direct"

    plan_steps = _build_plan_steps(state, execution)
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
    elif actionable_steps:
        execution["mode"] = "direct"


def _update_primary_progress_from_tool(
    state: State,
    execution: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    tool_name = str(entry.get("tool_name") or "").strip()
    step_map = {
        "chat_history_tail": "inspect_chat_history",
    }
    step_id = step_map.get(tool_name, "take_next_tool_step" if tool_name else None)
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
                "Respect the current task class in EXECUTION STATE. "
                "If the work required by that task class is complete, answer the user directly now. "
                "Otherwise call exactly one tool now."
            ),
        )

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
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
        execution = ensure_controller_execution_state(state, NODE_ID)
        execution["response_emitted"] = True
        execution["current_step"] = "complete"
        execution["missing_information"] = []
        execution["completion_ready"] = True
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
            build_initial_messages=_build_primary_agent_messages,
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
