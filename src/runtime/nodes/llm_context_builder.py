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
                "records": as_records(payload.get("items") if isinstance(payload, dict) else payload),
                "meta": payload.get("meta") if isinstance(payload, dict) else {},
            }
            replace_source_by_kind(ctx, kind="chat_turns", entry=entry)
            return

        if tool_name == "openmemory_query":
            entry = {
                "kind": "memories",
                "title": "Memory candidates",
                "records": as_records(payload),
                "meta": {},
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
                "meta": {},
            }
            replace_source_by_kind(ctx, kind="world_update", entry=entry)
            return

        entry = {
            "kind": "tool_result",
            "title": f"Tool result: {tool_name}",
            "records": as_records(payload),
            "meta": {},
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
