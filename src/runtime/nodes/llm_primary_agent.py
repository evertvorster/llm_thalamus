from __future__ import annotations

import json
import re
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common.context import build_loop_messages, build_runtime_context_messages
from runtime.nodes_common.execution_state import (
    build_invalid_output_feedback_payload,
    ensure_controller_execution_state,
)
from runtime.nodes_common.loop import run_default_node
from runtime.nodes_common.tools import (
    apply_world_update_tool_result,
    ensure_tool_transcript,
)
from runtime.providers.types import Message

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
    "take_next_tool_step": ("tool_call", "Use one retrieval or action tool if more evidence or work is needed."),
    "respond_to_user": ("final_response", "Respond directly to the user once the current request is complete."),
}

def _recent_chat_messages(state: State) -> list[Message]:
    out: list[Message] = []
    for msg in build_runtime_context_messages(
        state,
        node_id=NODE_ID,
        role_key=ROLE_KEY,
        include_bootstrap_system_messages=False,
    )[3:]:
        if msg.role not in {"user", "assistant"}:
            continue
        if msg.tool_calls:
            continue
        if msg.name is not None or msg.tool_call_id is not None:
            continue
        if not str(msg.content or "").strip():
            continue
        out.append(msg)
    return out


def _build_primary_agent_messages(state: State, builder) -> list[Message]:
    return build_loop_messages(
        state=state,
        builder=builder,
        node_id=NODE_ID,
        role_key=ROLE_KEY,
        system_prompt_name=PROMPT_NAME,
        task_message=Message(role="user", content=_current_user_text(state)),
        include_system_prompt=False,
        include_bootstrap_system_messages=False,
        include_bootstrap_messages=True,
        include_final_answer=False,
    )


def _world_has_authoritative_content(state: State) -> bool:
    world = state.get("world")
    return isinstance(world, dict) and bool(world)


def _bootstrap_prefill_tool_names(state: State) -> set[str]:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        return set()

    raw = rt.get("bootstrap_prefill_entries")
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


def _has_non_bootstrap_tool_result(state: State) -> bool:
    return bool(_tool_transcript_names(state))


def _has_action_result(state: State) -> bool:
    action_tools = {
        "world_apply_ops",
        "openmemory_store",
        "openmemory_delete",
        "openmemory_reinforce",
    }
    return bool(_tool_transcript_names(state) & action_tools)


def _has_retrieval_result(state: State) -> bool:
    retrieval_tools = {
        "chat_history_tail",
        "openmemory_query",
        "openmemory_get",
        "openmemory_list",
    }
    return bool((_bootstrap_prefill_tool_names(state) | _tool_transcript_names(state)) & retrieval_tools)


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
            "mutate ",
            "apply ",
            "remove ",
            "delete ",
            "add ",
            "update ",
            "change ",
            "store ",
            "save ",
            "write ",
            "tool call",
            "try that tool",
            "world state",
            "world apply ops",
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
        return _has_retrieval_result(state)
    if task_class == TASK_CLASS_ACTION_NEEDED:
        return _has_action_result(state)
    if task_class == TASK_CLASS_MULTI_STEP_PLAN:
        user_text = _current_user_text(state)
        if _is_explicit_plan_request(user_text):
            return has_world and (has_recent_chat or has_tool_evidence)
        return _has_non_bootstrap_tool_result(state)
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
    if task_class == TASK_CLASS_RETRIEVAL_NEEDED and not _has_retrieval_result(state):
        missing.append("retrieval_evidence")
    if task_class == TASK_CLASS_ACTION_NEEDED and not _has_action_result(state):
        missing.append("action_result")
    if task_class == TASK_CLASS_MULTI_STEP_PLAN and not _has_non_bootstrap_tool_result(state):
        missing.append("planned_intermediate_work")
    if task_class == TASK_CLASS_MULTI_STEP_PLAN and _is_explicit_plan_request(_current_user_text(state)):
        missing.append("plan_synthesis")
    deduped: list[str] = []
    for item in missing:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _planner_step_status(*, step_id: str, state: State, execution: dict[str, Any]) -> str:
    live_tools = _tool_transcript_names(state)
    last_action_name = str(execution.get("last_action_name") or "")
    last_action_status = str(execution.get("last_action_status") or "")

    if step_id == "take_next_tool_step":
        if live_tools:
            return "completed"
        if last_action_name not in {"", "none"} and last_action_name != "chat_history_tail" and last_action_status == "ok":
            return "in_progress"
    elif step_id == "respond_to_user":
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
    needs_tool_step = (
        task_class in {TASK_CLASS_RETRIEVAL_NEEDED, TASK_CLASS_ACTION_NEEDED, TASK_CLASS_MULTI_STEP_PLAN}
        and not _transcript_is_ready(state)
    )
    if needs_tool_step:
        desired_step_ids.append("take_next_tool_step")
    desired_step_ids.append("respond_to_user")

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


def _sync_primary_execution_state(state: State) -> None:
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
    execution["completion_condition"] = "Respond only when the work required by the current task class is complete."
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
    if pending_or_ready:
        execution["current_step"] = pending_or_ready[0]
    else:
        blocked_steps = [
            str(step.get("id") or "")
            for step in plan_steps
            if str(step.get("status") or "") == "blocked"
        ]
        execution["current_step"] = blocked_steps[0] if blocked_steps else "complete"

    actionable_steps = [
        step for step in plan_steps
        if str(step.get("id") or "") != "respond_to_user"
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
    step_id = "take_next_tool_step" if tool_name else None
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

    _sync_primary_execution_state(state)


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
        payload = safe_json_loads(result_text)
        if payload is None:
            return

        if apply_world_update_tool_result(
            state,
            node_id=NODE_ID,
            tool_name=tool_name,
            result_text=result_text,
        ):
            return

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
        return run_default_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="primary_agent",
            max_rounds=MAX_CONTEXT_ROUNDS,
            prepare_execution_state=_sync_primary_execution_state,
            build_initial_messages=_build_primary_agent_messages,
            apply_tool_result=apply_tool_result,
            build_invalid_output_feedback=_build_invalid_output_feedback,
            stop_when=None,
            on_tool_executed=_update_primary_progress_from_tool,
            replace_initial_system_message=True,
            insert_tool_transcript_before_final_user=False,
            allow_final_text=True,
            require_completion_ready_for_final_text=False,
            disable_tools_when_final_text_allowed=False,
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
