from __future__ import annotations

from typing import Any, Callable

from runtime.deps import Deps
from runtime.nodes_common.context import build_reflect_messages, recent_bootstrap_turns
from runtime.nodes_common.execution_state import ensure_planner_execution_state
from runtime.nodes_common.loop import run_reflect_node
from runtime.nodes_common.primitives import normalize_completion_sentinel
from runtime.nodes_common.tools import (
    apply_world_update_tool_result,
    filter_toolset,
)
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import ToolSet

NODE_ID = "llm.reflect_topics"
GROUP = "llm"
LABEL = "Reflect Topics"
PROMPT_NAME = "runtime_reflect_topics"
TASK_PROMPT_NAME = "runtime_reflect_topics_task"
ROLE_KEY = "reflect"
NODE_KEY_FOR_TOOLS = "reflect_topics"
MAX_ROUNDS = 6
RUNTIME_COMPLETE_KEY = "reflect_topics_complete"
RUNTIME_STATUS_KEY = "reflect_topics_status"
RUNTIME_RESULT_KEY = "reflect_topics_result"
NODE_STATUS_KEY = "reflect_topics"
COMPLETION_CONDITION = "Reply DONE only when topic maintenance is complete."
COMPLETION_SENTINEL = "DONE"

def _recent_turns_evidence(state: State, *, limit: int = 10) -> list[dict[str, str]]:
    return recent_bootstrap_turns(state, limit=limit)


def _prepare_reflect_evidence(state: State) -> None:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt
    rt["reflect_recent_turns"] = _recent_turns_evidence(state)


def _reflect_done(state: State) -> bool:
    rt = state.get("runtime", {})
    if not isinstance(rt, dict):
        return False
    return bool(rt.get(RUNTIME_COMPLETE_KEY, False))


def _world_topics(state: State) -> list[str]:
    world = state.get("world") or {}
    topics = world.get("topics") if isinstance(world, dict) else []
    if not isinstance(topics, list):
        return []
    return [str(topic).strip() for topic in topics if str(topic).strip()]


def _build_plan_steps(state: State) -> list[dict[str, Any]]:
    complete = _reflect_done(state)
    return [
        {
            "id": "update_topics_if_needed",
            "tool": "world_apply_ops",
            "purpose": "Update WORLD topics only if enduring topics clearly need correction.",
            "status": "completed" if complete else "ready",
        },
        {
            "id": "complete_reflection_topics",
            "tool": COMPLETION_SENTINEL,
            "purpose": "Finish the topic-reflect node by replying DONE once topic maintenance is complete.",
            "status": "completed" if complete else "ready",
        },
    ]


def _sync_execution_state(state: State) -> None:
    execution = ensure_planner_execution_state(state, NODE_ID)
    complete = _reflect_done(state)
    plan_steps = _build_plan_steps(state)
    execution["goal"] = "Perform required post-answer topic continuity maintenance and canonical topic updates."
    execution["mode"] = "direct"
    execution["completion_ready"] = complete
    execution["completion_ready_label"] = "TOPIC_MAINTENANCE_COMPLETE"
    execution["missing_items_label"] = "UNRESOLVED_ITEMS_JSON"
    execution["artifact_label"] = "WORLD_TOPICS"
    execution["terminal_action"] = COMPLETION_SENTINEL
    execution["completion_condition"] = COMPLETION_CONDITION
    execution["plan_steps"] = plan_steps
    execution["completed_steps"] = [
        str(step["id"]) for step in plan_steps if str(step.get("status")) == "completed"
    ]
    execution["current_step"] = "complete" if complete else "update_topics_if_needed"
    execution["missing_information"] = [] if complete else ["topic_maintenance_decision", "completion_decision"]
    execution["topics"] = _world_topics(state)


def _build_messages(state: State, builder) -> list[Message]:
    return build_reflect_messages(
        state=state,
        builder=builder,
        node_id=NODE_ID,
        role_key=ROLE_KEY,
        system_prompt_name=PROMPT_NAME,
        task_message=Message(role="user", content=builder.render_prompt(TASK_PROMPT_NAME)),
        include_bootstrap_system_messages=False,
        include_bootstrap_messages=False,
        include_recent_turns=True,
        recent_turn_limit=10,
        include_final_answer=True,
    )


def _toolset_for_round(state: State, default_toolset: ToolSet) -> ToolSet:
    _ = state
    return filter_toolset(
        default_toolset,
        allowed={"world_apply_ops"},
    )


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def _complete_topics(state: State, *, notes: str = "", issues: list[str] | None = None) -> None:
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt

        node_status = rt.setdefault("node_status", {})
        if not isinstance(node_status, dict):
            node_status = {}
            rt["node_status"] = node_status

        topics = _world_topics(state)
        out_topics = [str(x).strip() for x in topics if str(x).strip()]
        out_issues = [str(x).strip() for x in (issues or []) if str(x).strip()]
        out_notes = notes.strip()

        node_status[NODE_STATUS_KEY] = {
            "complete": True,
            "topics": out_topics,
            "issues": out_issues,
            "notes": out_notes,
        }
        rt[RUNTIME_COMPLETE_KEY] = True
        rt[RUNTIME_STATUS_KEY] = "ok"
        rt[RUNTIME_RESULT_KEY] = {
            "complete": True,
            "topics": out_topics,
            "issues": out_issues,
            "notes": out_notes,
        }

    def _build_invalid_output_hint(error_message: str) -> str:
        err = str(error_message or "")
        if '"tool"' in err or "output must be a JSON object" in err or "model produced no final output" in err:
            return (
                "Do not explain. Do not emit fake tool JSON. "
                "If topics still need an update, call world_apply_ops. "
                f"If topic maintenance is complete, reply exactly {COMPLETION_SENTINEL}."
            )
        return (
            "Do not explain. "
            "Use WORLD, RECENT TURNS, and EXECUTION_STATE to determine the next topic-maintenance action. "
            f"If topic maintenance is complete, reply exactly {COMPLETION_SENTINEL}; otherwise call world_apply_ops."
        )

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        apply_world_update_tool_result(
            state,
            node_id=NODE_ID,
            tool_name=tool_name,
            result_text=result_text,
        )

    def _complete_on_sentinel(state: State) -> None:
        _complete_topics(state)

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
            prepare_evidence=_prepare_reflect_evidence,
            prepare_execution_state=_sync_execution_state,
            build_task_message=lambda state, builder: Message(
                role="user",
                content=builder.render_prompt(TASK_PROMPT_NAME),
            ),
            toolset_for_round=_toolset_for_round,
            apply_tool_result=apply_tool_result,
            complete_on_sentinel=_complete_on_sentinel,
            build_invalid_output_hint=_build_invalid_output_hint,
            post_tool_guidance=(
                "Tool results above are evidence only. "
                f"If topic maintenance is now complete, reply exactly {COMPLETION_SENTINEL}. "
                "If more topic work remains, call world_apply_ops. "
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
