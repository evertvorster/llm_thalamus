from __future__ import annotations

from typing import Any, Sequence

from runtime.providers.types import Message
from runtime.tool_loop import ToolSet

from .primitives import stable_json


def ensure_controller_execution_state(state: dict, node_id: str) -> dict[str, Any]:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt

    execution = rt.setdefault("controller_execution", {})
    if not isinstance(execution, dict):
        execution = {}
        rt["controller_execution"] = execution

    node_state = execution.get(node_id)
    if not isinstance(node_state, dict):
        node_state = {}
        execution[node_id] = node_state
    return node_state


def reset_controller_execution_state(state: dict, node_id: str) -> None:
    execution = ensure_controller_execution_state(state, node_id)
    execution.clear()
    execution.update(
        {
            "current_round": 1,
            "last_action_name": "none",
            "last_action_kind": "none",
            "last_action_status": "none",
        }
    )


def ensure_planner_execution_state(state: dict, node_id: str) -> dict[str, Any]:
    execution = ensure_controller_execution_state(state, node_id)
    task = state.get("task") or {}
    goal = str(task.get("user_text") or "").strip()

    execution.setdefault("goal", goal)
    execution.setdefault("mode", "direct")
    execution.setdefault("completion_ready", False)
    execution.setdefault("missing_information", [])
    execution.setdefault("plan_steps", [])
    execution.setdefault("current_step", "")
    execution.setdefault("completed_steps", [])
    execution.setdefault("completion_ready_label", "COMPLETION_READY")
    execution.setdefault("missing_items_label", "MISSING_INFORMATION_JSON")
    execution.setdefault("artifact_label", "ARTIFACT")
    execution.setdefault("terminal_action", "complete")
    execution.setdefault(
        "completion_condition",
        "Call the terminal action only when the node's work is complete.",
    )
    return execution


def _stable_json_or_fallback(value: Any, *, fallback: str) -> str:
    try:
        return stable_json(value)
    except Exception:
        return fallback


def render_world_state_message(state: dict) -> str:
    world = state.get("world")
    if not isinstance(world, dict):
        world = {}
    return "WORLD_STATE_JSON\n" + _stable_json_or_fallback(world, fallback="{}")


def render_available_tools(toolset: ToolSet | None) -> str:
    if toolset is None or not getattr(toolset, "descriptors", None):
        return (
            "AVAILABLE TOOLS\n"
            "No tools are available for this node.\n"
        )

    parts: list[str] = [
        "AVAILABLE TOOLS",
        "The entries below are the live tools exposed for this node run.",
        "Use their real names and follow their current descriptions and parameter schemas.",
        "",
    ]

    for tool_name in sorted(toolset.descriptors.keys()):
        descriptor = toolset.descriptors[tool_name]
        parts.extend(
            [
                f"TOOL: {descriptor.public_name}",
                "DESCRIPTION:",
                str(descriptor.description or "").strip() or "(no description provided)",
                "PARAMETERS_JSON:",
                _stable_json_or_fallback(descriptor.parameters, fallback="{}"),
                "",
            ]
        )

    return "\n".join(parts).rstrip()


def render_node_control_state_json(state: dict, node_id: str, *, role_key: str = "") -> str:
    if node_id == "llm.primary_agent":
        control = ensure_controller_execution_state(state, node_id)
    elif role_key in {"planner", "reflect"}:
        control = ensure_planner_execution_state(state, node_id)
    else:
        control = ensure_controller_execution_state(state, node_id)
    return "NODE_CONTROL_STATE_JSON\n" + _stable_json_or_fallback(control, fallback="{}")


def render_planner_execution_state(state: dict, node_id: str) -> str:
    execution = ensure_planner_execution_state(state, node_id)
    current_round = execution.get("current_round", 1)
    last_name = str(execution.get("last_action_name") or "none")
    last_kind = str(execution.get("last_action_kind") or "none")
    last_status = str(execution.get("last_action_status") or "none")

    goal = str(execution.get("goal") or "").strip()
    mode = str(execution.get("mode") or "direct").strip() or "direct"
    completion_ready = bool(execution.get("completion_ready", False))
    current_step = str(execution.get("current_step") or "").strip() or "none"
    completion_condition = str(execution.get("completion_condition") or "").strip()
    missing_information = execution.get("missing_information")
    completed_steps = execution.get("completed_steps")
    plan_steps = execution.get("plan_steps")
    completion_ready_label = str(execution.get("completion_ready_label") or "COMPLETION_READY").strip() or "COMPLETION_READY"
    missing_items_label = str(execution.get("missing_items_label") or "MISSING_INFORMATION_JSON").strip() or "MISSING_INFORMATION_JSON"
    artifact_label = str(execution.get("artifact_label") or "ARTIFACT").strip() or "ARTIFACT"
    terminal_action = str(execution.get("terminal_action") or "complete").strip() or "complete"

    return (
        "EXECUTION STATE\n"
        f"NODE_RUN: {node_id}\n"
        f"CURRENT_ROUND: {current_round}\n"
        "\n"
        "LAST_ACTION:\n"
        f"- NAME: {last_name}\n"
        f"- KIND: {last_kind}\n"
        f"- STATUS: {last_status}\n"
        "\n"
        "PLANNER WORKING STATE:\n"
        f"- GOAL: {goal}\n"
        f"- MODE: {mode}\n"
        f"- {completion_ready_label}: {str(completion_ready).lower()}\n"
        f"- CURRENT_STEP: {current_step}\n"
        f"- COMPLETION_CONDITION: {completion_condition}\n"
        f"{missing_items_label}:\n"
        f"{_stable_json_or_fallback(missing_information, fallback='[]')}\n"
        "COMPLETED_STEPS_JSON:\n"
        f"{_stable_json_or_fallback(completed_steps, fallback='[]')}\n"
        "PLAN_STEPS_JSON:\n"
        f"{_stable_json_or_fallback(plan_steps, fallback='[]')}\n"
        "\n"
        "PROGRESS:\n"
        "- PLAN_STEPS_JSON is your working plan and progress record for this node run\n"
        "- TOOL_TRANSCRIPT entries are execution evidence only\n"
        "- WORLD and the runtime state blocks above are canonical current state\n"
        f"- Keep the plan in execution state, not in {artifact_label}\n"
        "\n"
        "NEXT ACTION RULE:\n"
        "Your next response must be exactly one action.\n"
        f"Allowed: one tool call or {terminal_action}.\n"
        f"If {completion_ready_label.lower()} is true, call {terminal_action} now.\n"
        "Otherwise execute exactly one next plan step."
    )


def render_primary_agent_execution_state(state: dict, node_id: str) -> str:
    execution = ensure_planner_execution_state(state, node_id)
    current_round = execution.get("current_round", 1)
    last_name = str(execution.get("last_action_name") or "none")
    last_kind = str(execution.get("last_action_kind") or "none")
    last_status = str(execution.get("last_action_status") or "none")
    mode = str(execution.get("mode") or "direct").strip() or "direct"
    task_class = str(execution.get("task_class") or "unknown").strip() or "unknown"
    completion_ready = bool(execution.get("completion_ready", False))
    current_step = str(execution.get("current_step") or "").strip() or "none"
    missing_information = execution.get("missing_information")
    completed_steps = execution.get("completed_steps")
    plan_steps = execution.get("plan_steps")

    return (
        "EXECUTION STATE\n"
        f"NODE_RUN: {node_id}\n"
        f"CURRENT_ROUND: {current_round}\n"
        "\n"
        "PRIMARY WORKING STATE:\n"
        f"- TASK_CLASS: {task_class}\n"
        f"MODE: {mode}\n"
        f"COMPLETION_READY: {str(completion_ready).lower()}\n"
        f"CURRENT_STEP: {current_step}\n"
        "\n"
        "LAST_ACTION:\n"
        f"- NAME: {last_name}\n"
        f"- KIND: {last_kind}\n"
        f"- STATUS: {last_status}\n"
        "\n"
        "MISSING_INFORMATION_JSON:\n"
        f"{_stable_json_or_fallback(missing_information, fallback='[]')}\n"
        "COMPLETED_STEPS_JSON:\n"
        f"{_stable_json_or_fallback(completed_steps, fallback='[]')}\n"
        "PLAN_STEPS_JSON:\n"
        f"{_stable_json_or_fallback(plan_steps, fallback='[]')}"
    )


def render_execution_state(state: dict, node_id: str, *, role_key: str = "") -> str:
    if node_id == "llm.primary_agent":
        return render_primary_agent_execution_state(state, node_id)

    if role_key in {"planner", "reflect"}:
        return render_planner_execution_state(state, node_id)

    execution = ensure_controller_execution_state(state, node_id)
    current_round = execution.get("current_round", 1)
    last_name = str(execution.get("last_action_name") or "none")
    last_kind = str(execution.get("last_action_kind") or "none")
    last_status = str(execution.get("last_action_status") or "none")

    next_action_rule = "Your next response must be exactly one valid action for this node."

    return (
        "EXECUTION STATE\n"
        f"NODE_RUN: {node_id}\n"
        f"CURRENT_ROUND: {current_round}\n"
        "\n"
        "LAST_ACTION:\n"
        f"- NAME: {last_name}\n"
        f"- KIND: {last_kind}\n"
        f"- STATUS: {last_status}\n"
        "\n"
        "PROGRESS:\n"
        "- TOOL_TRANSCRIPT entries are execution history only\n"
        "- WORLD and the runtime state blocks above are canonical current state\n"
        "- The previous action, if any, has already been applied to state\n"
        "\n"
        "NEXT ACTION RULE:\n"
        f"{next_action_rule}"
    )


def build_invalid_output_feedback_payload(
    *,
    allowed_actions: Sequence[str],
    last_tool: str | None,
    node_hint: str | None = None,
) -> dict[str, Any]:
    allowed = [str(action).strip() for action in allowed_actions if str(action).strip()]
    forbidden = [
        "natural_language",
        "explanation",
        "summary",
        "apology",
        "narration",
        "multiple_actions",
    ]

    payload: dict[str, Any] = {
        "error_type": "invalid_node_output",
        "status": "rejected",
        "rejected": True,
        "executed": False,
        "message": "Previous output was rejected and not executed.",
        "instruction": "Respond with exactly one valid action now.",
        "required_response": "exactly_one_action",
        "allowed_actions": allowed,
        "forbidden": forbidden,
        "failure_warning": "If you emit plain text again, this node will fail again.",
    }
    if isinstance(last_tool, str) and last_tool.strip():
        payload["last_tool"] = last_tool.strip()
    if isinstance(node_hint, str) and node_hint.strip():
        payload["node_hint"] = node_hint.strip()
    return payload
