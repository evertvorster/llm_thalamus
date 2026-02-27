from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

from runtime.nodes_common import stable_json, run_structured_node


NODE_ID = "llm.memory_retriever"
GROUP = "llm"
LABEL = "Memory Retriever"
PROMPT_NAME = "runtime_memory_retriever"
ROLE_KEY = "reflect"


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def apply_result(state: State, obj: dict) -> None:
        did_query = bool(obj.get("did_query"))
        query_text = str(obj.get("query_text", "") or "")
        desired_n = obj.get("desired_n", None)
        items = obj.get("items", [])

        try:
            desired_n_int = int(desired_n) if desired_n is not None else 0
        except Exception:
            desired_n_int = 0

        returned_n = len(items) if isinstance(items, list) else 0

        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        if did_query:
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
                    "kind": "memories",
                    "title": "Relevant long-term memories",
                    "items": items,
                    "meta": {
                        "query_text": query_text,
                        "requested_limit": desired_n_int,
                        "returned": returned_n,
                    },
                }
            )

            issues = ctx.get("issues")
            if not isinstance(issues, list):
                issues = []
                ctx["issues"] = issues
            issues.append(
                f"memory_retriever: did_query=true query={query_text!r} returned={returned_n}"
            )
        else:
            issues = ctx.get("issues")
            if not isinstance(issues, list):
                issues = []
                ctx["issues"] = issues
            issues.append("memory_retriever: did_query=false (topics not relevant)")

    def node(state: State) -> State:
        user_text = str(state.get("task", {}).get("user_text", "") or "")

        world = state.get("world", {}) or {}
        world_json = stable_json(world)

        topics = world.get("topics", []) or []
        topics_json = json.dumps(topics, ensure_ascii=False)

        context_obj = state.get("context", {}) or {}
        context_json = stable_json(context_obj)

        # Requested limit (k) comes from context_builder's memory_request packet.
        mr = {}
        if isinstance(context_obj, dict):
            mr = context_obj.get("memory_request", {}) or {}
        requested_limit = 0
        if isinstance(mr, dict):
            requested_limit = mr.get("k", 0)
        try:
            requested_limit = int(requested_limit)
        except Exception:
            requested_limit = 0

        now_iso = str(state.get("runtime", {}).get("now_iso", "") or "")
        timezone = str(state.get("runtime", {}).get("timezone", "") or "")

        tokens = {
            "NODE_ID": NODE_ID,
            "ROLE_KEY": ROLE_KEY,
            "USER_MESSAGE": user_text,
            "WORLD_JSON": world_json,
            "TOPICS_JSON": topics_json,
            "CONTEXT_JSON": context_json,
            "NOW_ISO": now_iso,
            "TIMEZONE": timezone,
            "REQUESTED_LIMIT": str(requested_limit),
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
            node_key_for_tools="memory_retriever",
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