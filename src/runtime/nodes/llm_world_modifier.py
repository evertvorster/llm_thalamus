from __future__ import annotations

import json
from typing import Any, Callable, Dict

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

from runtime.nodes_common import stable_json, run_controller_node, parse_first_json_object


NODE_ID = "llm.world_modifier"
GROUP = "llm"
LABEL = "World Modifier"
PROMPT_NAME = "runtime_world_modifier"
ROLE_KEY = "planner"


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def tokens_for_round(state: State, _round_idx: int) -> Dict[str, str]:
        user_text = str((state.get("task") or {}).get("user_text", "") or "")
        world_json = stable_json(state.get("world") or {})
        return {
            "USER_MESSAGE": user_text,
            "WORLD_JSON": world_json,
            "NODE_ID": NODE_ID,
            "ROLE_KEY": ROLE_KEY,
        }

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        # world_modifier tools may return a JSON object that includes a full "world" replacement.
        tool_obj = _safe_json_loads(result_text)
        if isinstance(tool_obj, dict) and isinstance(tool_obj.get("world"), dict):
            state["world"] = tool_obj["world"]
            # Emit a mid-turn world update for the UI (best-effort)
            try:
                emitter = (state.get("runtime") or {}).get("emitter")
                if emitter is not None:
                    emitter.world_update(node_id=NODE_ID, span_id=None, world=state.get("world", {}) or {})
            except Exception:
                pass

    def apply_handoff(state: State, obj: dict) -> bool:
        # Persist the structured output for debugging and set status summary
        state.setdefault("runtime", {})["world_modifier"] = obj
        summary = str(obj.get("summary", "") or "").strip()
        if summary:
            state.setdefault("runtime", {})["status"] = summary

        # Always stop after one controller pass (tool loop already multi-steps internally).
        return True

    def node(state: State) -> State:
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="world_modifier",
            tokens_for_round=tokens_for_round,
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            max_rounds=1,
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
