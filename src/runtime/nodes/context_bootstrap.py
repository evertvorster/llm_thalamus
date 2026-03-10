from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    append_node_trace,
    as_records,
    get_emitter,
    replace_source_by_kind,
    run_tools_mechanically,
)

NODE_ID = "context.bootstrap"
GROUP = "context"
LABEL = "Context Bootstrap"
ROLE_KEY = ""


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

    for topic in topics[:8]:
        if isinstance(topic, str) and topic.strip():
            parts.append(topic.strip())

    return " | ".join(parts).strip()


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def node(state: State) -> State:
        append_node_trace(state, NODE_ID)

        emitter = get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            ctx = state.setdefault("context", {})
            if not isinstance(ctx, dict):
                ctx = {}
                state["context"] = ctx

            toolset = services.tools.toolset_for_node("context_bootstrap")

            calls: list[tuple[str, dict]] = [
                ("chat_history_tail", {"limit": 4}),
            ]

            world = state.get("world", {})
            if not isinstance(world, dict):
                world = {}

            query = _topic_query_from_world(world)
            if query:
                calls.append(("openmemory_query", {"query": query, "k": 6}))

            tool_msgs = run_tools_mechanically(
                toolset=toolset,
                calls=calls,
                emitter=emitter,
                node_id=NODE_ID,
                span_id=getattr(span, "span_id", None),
            )

            for msg in tool_msgs:
                payload = _safe_json_loads(msg.content or "")
                if payload is None:
                    continue

                tool_name = msg.name or ""

                if tool_name == "chat_history_tail":
                    entry = {
                        "kind": "chat_turns",
                        "title": "Recent chat turns",
                        "records": as_records(payload.get("items") if isinstance(payload, dict) else payload),
                        "meta": payload.get("meta") if isinstance(payload, dict) else {},
                    }
                    replace_source_by_kind(ctx, kind="chat_turns", entry=entry)
                    continue

                if tool_name == "openmemory_query":
                    entry = {
                        "kind": "memories",
                        "title": "Memory candidates",
                        "records": as_records(payload),
                        "meta": {},
                    }
                    replace_source_by_kind(ctx, kind="memories", entry=entry)
                    continue

                entry = {
                    "kind": "tool_result",
                    "title": f"Tool result: {tool_name}",
                    "records": as_records(payload),
                    "meta": {},
                }
                replace_source_by_kind(ctx, kind="tool_result", entry=entry)

            rt = state.setdefault("runtime", {})
            if not isinstance(rt, dict):
                rt = {}
                state["runtime"] = rt

            rt["context_bootstrap_status"] = "ok"
            rt["context_bootstrap_seeded"] = True

            span.end_ok()
            return state

        except Exception as e:
            span.end_error(code="NODE_ERROR", message=str(e))
            raise

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role=ROLE_KEY,
        make=make,
        prompt_name=None,
    )
)
