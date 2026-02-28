from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

from runtime.nodes_common import stable_json, run_structured_node


NODE_ID = "llm.memory_writer"
GROUP = "llm"
LABEL = "Memory Writer"
PROMPT_NAME = "runtime_memory_writer"
ROLE_KEY = "reflect"


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def apply_result(state: State, obj: dict) -> None:
        stored = obj.get("stored", [])
        stored_count = obj.get("stored_count", None)

        if isinstance(stored_count, int):
            stored_n = stored_count
        elif isinstance(stored, list):
            stored_n = len(stored)
        else:
            stored_n = 0

        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        issues = ctx.get("issues")
        if not isinstance(issues, list):
            issues = []
            ctx["issues"] = issues
        issues.append(f"memory_writer: stored_count={stored_n}")

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
                "items": [{"stored_count": stored_n}],
            }
        )

    def node(state: State) -> State:
        user_text = str(state.get("task", {}).get("user_text", "") or "")
        answer_text = str(state.get("final", {}).get("answer", "") or "")

        world = state.get("world", {}) or {}
        world_json = stable_json(world)

        topics = world.get("topics", []) or []
        topics_json = json.dumps(topics, ensure_ascii=False)

        context_json = stable_json(state.get("context", {}) or {})

        now_iso = str(state.get("runtime", {}).get("now_iso", "") or "")
        timezone = str(state.get("runtime", {}).get("timezone", "") or "")

        tokens = {
            "NODE_ID": NODE_ID,
            "ROLE_KEY": ROLE_KEY,
            "USER_MESSAGE": user_text,
            "ASSISTANT_ANSWER": answer_text,
            "WORLD_JSON": world_json,
            "TOPICS_JSON": topics_json,
            "CONTEXT_JSON": context_json,
            "NOW_ISO": now_iso,
            "TIMEZONE": timezone,
        }

        return run_structured_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            tokens=tokens,
            node_key_for_tools="memory_writer",
            apply_result=apply_result,
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
