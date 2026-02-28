from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

from runtime.nodes_common import get_emitter, stable_json, run_structured_node, run_tools_mechanically


NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_NAME = "runtime_router"  # resources/prompts/runtime_router.txt


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _topic_query_from_world(world: dict[str, Any]) -> str:
    topics = world.get("topics")
    if not isinstance(topics, list):
        topics = []

    parts: list[str] = []
    project = world.get("project")
    if isinstance(project, str) and project.strip():
        parts.append(project.strip())

    for t in topics[:8]:
        if isinstance(t, str) and t.strip():
            parts.append(t.strip())

    return " | ".join(parts).strip()


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        # Mechanical prefill (fast path): use the same tool handlers as tool loop.
        emitter = get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            ctx = state.setdefault("context", {})
            if not isinstance(ctx, dict):
                ctx = {}
                state["context"] = ctx

            sources = ctx.setdefault("sources", [])
            if not isinstance(sources, list):
                sources = []
                ctx["sources"] = sources

            toolset = services.tools.toolset_for_node("router")

            calls: list[tuple[str, dict]] = [("chat_history_tail", {"limit": 4})]

            world = state.get("world", {}) or {}
            q = _topic_query_from_world(world if isinstance(world, dict) else {})
            if q:
                calls.append(("memory_query", {"query": q, "k": 6}))

            tool_msgs = run_tools_mechanically(
                toolset=toolset,
                calls=calls,
                emitter=emitter,
                node_id=NODE_ID,
                span_id=getattr(span, "span_id", None),
            )

            # Apply prefill messages into context.sources (append; router seed only)
            for m in tool_msgs:
                obj = _safe_json_loads(m.content or "")
                if isinstance(obj, dict):
                    sources.append(obj)

            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world_json = stable_json(world if isinstance(world, dict) else {})
            existing_context_json = stable_json(state.get("context", {}) or {})

            now = str(state.get("runtime", {}).get("now_iso", "") or "")
            tz = str(state.get("runtime", {}).get("timezone", "") or "")

            tokens = {
                "USER_MESSAGE": user_text,
                "WORLD_JSON": world_json,
                "EXISTING_CONTEXT_JSON": existing_context_json,
                "NOW": now,
                "TZ": tz,
            }


            def apply_result(st: State, obj: dict) -> None:
                # Router contract: store route decision under state['task']['route'] and/or ctx fields.
                route = obj.get("route")
                if isinstance(route, str) and route.strip():
                    st.setdefault("task", {})["route"] = route.strip()
                # Router may also return issues
                if isinstance(obj.get("issues"), list):
                    st.setdefault("runtime", {})["issues"] = obj.get("issues")

            # Single-pass routing decision. No tools in this LLM call (prefill already done).
            return run_structured_node(
                state=state,
                deps=deps,
                services=services,
                node_id=NODE_ID,
                label=LABEL,
                role_key="router",
                prompt_name=PROMPT_NAME,
                tokens=tokens,
                node_key_for_tools=None,
                tools_override=None,
                response_format_override=deps.get_llm("router").response_format,
                apply_result=apply_result,
            )

        except Exception as e:
            span.end_error(code="NODE_ERROR", message=str(e))
            raise

    return node


register(NodeSpec(
    node_id=NODE_ID,
    group=GROUP,
    label=LABEL,
    role="router",
    make=make,
    prompt_name=PROMPT_NAME,
))
