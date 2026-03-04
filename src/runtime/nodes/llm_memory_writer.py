from __future__ import annotations
import json
from typing import Any, Callable, Dict
from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import stable_json, run_controller_node

NODE_ID = "llm.memory_writer"
GROUP = "llm"
LABEL = "Memory Writer"
PROMPT_NAME = "runtime_memory_writer"
ROLE_KEY = "reflect"

def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None

def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        # memory_store tool returns confirmation of stored memory
        tool_obj = _safe_json_loads(result_text)
        # Track stored memories for final summary
        stored = state.setdefault("_memory_writer_stored", [])
        if isinstance(tool_obj, dict) and tool_obj.get("ok"):
            stored.append(tool_obj)

    def apply_handoff(state: State, obj: dict) -> bool:
        # Persist the structured output for debugging
        stored_count = obj.get("stored_count", 0)
        stored = obj.get("stored", [])

        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        issues = ctx.get("issues")
        if not isinstance(issues, list):
            issues = []
            ctx["issues"] = issues
        issues.append(f"memory_writer: stored_count={stored_count}")

        # Keep existing diagnostic placement (legacy): ctx["context"]["sources"]
        ctx_inner = ctx.get("context")
        if not isinstance(ctx_inner, dict):
            ctx_inner = {}
            ctx["context"] = ctx_inner

        sources = ctx_inner.get("sources")
        if not isinstance(sources, list):
            sources = []
            ctx_inner["sources"] = sources

        sources.append(
            {
                "kind": "notes",
                "title": "Memory writer status",
                "items": [{"stored_count": stored_count}],
            }
        )

        # Clean up temporary state
        state.pop("_memory_writer_stored", None)

        # Always stop after one controller pass (tool loop already multi-steps internally)
        return True

    def node(state: State) -> State:
        # TokenBuilder handles prompt rendering automatically via GLOBAL_TOKEN_SPEC
        # State is re-evaluated each round, so tokens reflect current context
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="memory_writer",
            tokens_for_round=None,  # Registry handles it
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