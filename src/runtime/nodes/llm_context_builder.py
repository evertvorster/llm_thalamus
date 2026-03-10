from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    as_records,
    replace_source_by_kind,
    run_controller_node,
)

NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"
MAX_CONTEXT_ROUNDS = 10


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_memory_records(payload: Any) -> list[Any]:
    records: list[Any] = []
    if not isinstance(payload, dict):
        return records

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

    return records


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        payload = _safe_json_loads(result_text)
        if payload is None:
            return

        if tool_name == "chat_history_tail":
            entry = {
                "kind": "chat_turns",
                "title": "Recent chat turns",
                "records": as_records(payload.get("records") if isinstance(payload, dict) else payload),
            }
            replace_source_by_kind(ctx, kind="chat_turns", entry=entry)
            return

        if tool_name == "openmemory_query":
            entry = {
                "kind": "memories",
                "title": "Memory candidates",
                "records": _normalize_memory_records(payload),
            }
            replace_source_by_kind(ctx, kind="memories", entry=entry)
            return

        if tool_name == "world_apply_ops":
            if isinstance(payload, dict) and isinstance(payload.get("world"), dict):
                state["world"] = payload["world"]
                try:
                    emitter = (state.get("runtime") or {}).get("emitter")
                    if emitter is not None:
                        emitter.world_update(
                            node_id=NODE_ID,
                            span_id=None,
                            world=state.get("world", {}) or {},
                        )
                except Exception:
                    pass

            entry = {
                "kind": "world_update",
                "title": "World update result",
                "records": as_records(payload),
            }
            replace_source_by_kind(ctx, kind="world_update", entry=entry)
            return

        entry = {
            "kind": "tool_result",
            "title": f"Tool result: {tool_name}",
            "records": as_records(payload),
        }
        replace_source_by_kind(ctx, kind="tool_result", entry=entry)

    def apply_handoff(state: State, obj: dict) -> bool:
        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        complete = bool(obj.get("complete", False))

        nxt = obj.get("next")
        if not isinstance(nxt, str) or not nxt.strip():
            nxt = "answer"
        nxt = nxt.strip().lower()
        if nxt not in ("answer", "planner"):
            nxt = "answer"

        issues = obj.get("issues")
        if isinstance(issues, list):
            ctx["issues"] = [str(x) for x in issues]

        notes = obj.get("notes")
        if isinstance(notes, str) and notes.strip():
            ctx["notes"] = notes.strip()

        ctx["complete"] = complete
        if complete:
            ctx["next"] = nxt
        else:
            ctx["next"] = "context_builder"

        rt = state.setdefault("runtime", {})
        rt["context_builder_complete"] = complete
        rt["context_builder_next"] = ctx["next"]
        rt["context_builder_status"] = "ok" if len(ctx.get("sources") or []) > 0 else "insufficient_data"

        return complete

    def node(state: State) -> State:
        return run_controller_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools="context_builder",
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            max_rounds=MAX_CONTEXT_ROUNDS,
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
