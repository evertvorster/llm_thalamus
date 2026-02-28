from __future__ import annotations

import json
from typing import Any, Callable, Dict

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

from runtime.nodes_common import (
    stable_json,
    run_controller_node,
    replace_source_by_kind,
    as_records,
)


NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"

MAX_CONTEXT_ROUNDS = 5


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def tokens_for_round(state: State, _round_idx: int) -> Dict[str, str]:
        user_text = str((state.get("task") or {}).get("user_text", "") or "")
        world_json = stable_json(state.get("world") or {})
        existing_context_json = stable_json(state.get("context") or {})
        return {
            "USER_MESSAGE": user_text,
            "WORLD_JSON": world_json,
            "EXISTING_CONTEXT_JSON": existing_context_json,
            "NODE_ID": NODE_ID,
            "ROLE_KEY": ROLE_KEY,
        }

    def apply_tool_result(state: State, tool_name: str, result_text: str) -> None:
        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        # We store evidence under context.sources using canonical kinds.
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

        if tool_name == "memory_query":
            entry = {
                "kind": "memories",
                "title": "Memory candidates",
                "records": as_records(payload),
                "meta": {},
            }
            replace_source_by_kind(ctx, kind="memories", entry=entry)
            return

        # Fallback: keep last generic tool result
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
        if nxt not in ("answer", "memory_retriever", "planner"):
            nxt = "answer"

        ctx["complete"] = complete
        ctx["next"] = nxt

        # optional issues
        issues = obj.get("issues")
        if isinstance(issues, list):
            ctx["issues"] = [str(x) for x in issues]
        # optional notes
        notes = obj.get("notes")
        if isinstance(notes, str) and notes.strip():
            ctx["notes"] = notes.strip()

        # optional memory_request for downstream retriever
        mr = obj.get("memory_request")
        if isinstance(mr, dict):
            q = mr.get("query")
            k = mr.get("k")
            if isinstance(q, str) and q.strip():
                out = {"query": q.strip()}
                try:
                    kk = int(k)
                    if 1 <= kk <= 16:
                        out["k"] = kk
                except Exception:
                    pass
                ctx["memory_request"] = out

        # maintain legacy runtime keys if downstream relies on them
        rt = state.setdefault("runtime", {})
        rt["context_builder_complete"] = complete
        rt["context_builder_next"] = nxt
        rt["context_builder_status"] = "ok" if len(ctx.get("sources") or []) > 0 else "insufficient_data"

        return complete or nxt in ("answer", "planner", "memory_retriever")

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
            tokens_for_round=tokens_for_round,
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
