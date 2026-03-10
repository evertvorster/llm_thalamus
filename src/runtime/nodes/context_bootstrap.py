from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    append_node_trace,
    get_emitter,
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


def _normalize_chat_turn_source(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    records = payload.get("records")
    if not isinstance(records, list):
        return None

    return {
        "kind": "chat_turns",
        "title": "Recent chat turns",
        "records": records,
    }


def _normalize_memory_source(payload: Any) -> dict[str, Any] | None:
    records: list[Any] = []
    if isinstance(payload, dict):
        text = payload.get("text")
        raw = payload.get("raw")
        content = payload.get("content")

        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    records = parsed
                elif parsed is not None:
                    records = [parsed]
            except Exception:
                records = [{"text": text.strip()}]

        if not records and isinstance(raw, dict):
            result = raw.get("result")
            if isinstance(result, dict):
                if isinstance(result.get("memories"), list):
                    records = result.get("memories") or []
                elif isinstance(result.get("results"), list):
                    records = result.get("results") or []
                elif isinstance(result.get("data"), list):
                    records = result.get("data") or []
                elif result:
                    records = [result]
            elif raw:
                records = [raw]

        if not records and isinstance(content, list):
            text_blocks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_blocks.append(item["text"])
            if text_blocks:
                records = [{"text": "\n".join(text_blocks).strip()}]

    return {
        "kind": "memories",
        "title": "Memory candidates",
        "records": records,
    }


def _apply_context_op(
    *,
    toolset,
    ctx: dict[str, Any],
    op: dict[str, Any],
    emitter,
    node_id: str,
    span_id: str | None,
) -> dict[str, Any]:
    apply_msgs = run_tools_mechanically(
        toolset=toolset,
        calls=[("context_apply_ops", {"context": ctx, "ops": [op]})],
        emitter=emitter,
        node_id=node_id,
        span_id=span_id,
    )
    if not apply_msgs:
        raise RuntimeError("context_bootstrap: context_apply_ops unavailable")

    result = _safe_json_loads(apply_msgs[0].content or "")
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"context_bootstrap: context_apply_ops failed: {result}")

    updated = result.get("context")
    if not isinstance(updated, dict):
        raise RuntimeError("context_bootstrap: context_apply_ops returned invalid context")

    return updated


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
                    entry = _normalize_chat_turn_source(payload)
                    if entry is None:
                        continue
                    ctx = _apply_context_op(
                        toolset=toolset,
                        ctx=ctx,
                        op={"op": "upsert_source", "source": entry},
                        emitter=emitter,
                        node_id=NODE_ID,
                        span_id=getattr(span, "span_id", None),
                    )
                    state["context"] = ctx
                    continue

                if tool_name == "openmemory_query":
                    entry = _normalize_memory_source(payload)
                    if entry is None:
                        continue
                    ctx = _apply_context_op(
                        toolset=toolset,
                        ctx=ctx,
                        op={"op": "upsert_source", "source": entry},
                        emitter=emitter,
                        node_id=NODE_ID,
                        span_id=getattr(span, "span_id", None),
                    )
                    state["context"] = ctx
                    continue

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
