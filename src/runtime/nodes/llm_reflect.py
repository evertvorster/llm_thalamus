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

NODE_ID = "llm.reflect"
GROUP = "llm"
LABEL = "Reflect"
PROMPT_NAME = "runtime_reflect"
ROLE_KEY = "reflect"


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
                "title": "Topic update result",
                "records": as_records(payload),
                "meta": {},
            }
            replace_source_by_kind(ctx, kind="world_update", entry=entry)
            return

        if tool_name == "memory_store":
            if isinstance(payload, dict) and payload.get("ok"):
                stored_count = state.get("_reflect_stored_count", 0)
                if not isinstance(stored_count, int):
                    stored_count = 0
                state["_reflect_stored_count"] = stored_count + 1
            return

        entry = {
            "kind": "tool_result",
            "title": f"Tool result: {tool_name}",
            "records": as_records(payload),
            "meta": {},
        }
        replace_source_by_kind(ctx, kind="tool_result", entry=entry)

    def apply_handoff(state: State, obj: dict) -> bool:
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt

        ctx = state.setdefault("context", {})
        if not isinstance(ctx, dict):
            ctx = {}
            state["context"] = ctx

        complete = bool(obj.get("complete", True))
        issues = obj.get("issues")
        notes = obj.get("notes")
        topics = obj.get("topics")
        stored = obj.get("stored")
        stored_count = obj.get("stored_count")

        if isinstance(issues, list):
            ctx["issues"] = [str(x) for x in issues]

        if isinstance(notes, str) and notes.strip():
            ctx["notes"] = notes.strip()

        actual_stored_count = state.pop("_reflect_stored_count", 0)
        if not isinstance(actual_stored_count, int):
            actual_stored_count = 0

        rt["reflect_complete"] = complete
        rt["reflect_status"] = "ok"
        rt["reflect_stored_count"] = actual_stored_count

        result_summary: dict[str, Any] = {
            "complete": complete,
            "stored_count": actual_stored_count,
        }

        if isinstance(topics, list):
            result_summary["topics"] = [str(x) for x in topics]

        if isinstance(stored_count, int):
            result_summary["reported_stored_count"] = stored_count

        if isinstance(stored, list):
            result_summary["stored"] = stored

        if isinstance(issues, list):
            result_summary["issues"] = [str(x) for x in issues]

        if isinstance(notes, str) and notes.strip():
            result_summary["notes"] = notes.strip()

        rt["reflect_result"] = result_summary

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
            node_key_for_tools="reflect",
            apply_tool_result=apply_tool_result,
            apply_handoff=apply_handoff,
            max_rounds=1,
        )

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role=ROLE_KEY,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)