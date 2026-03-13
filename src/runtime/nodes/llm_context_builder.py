from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    as_records,
    build_invalid_output_feedback_payload,
    replace_source_by_kind,
    run_controller_node,
)

NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"
MAX_CONTEXT_ROUNDS = 10
ALLOWED_ROUTE_TARGETS = {"answer"}
ALLOWED_ROUTE_STATUS = {"complete", "incomplete", "blocked"}


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
    def _route_done(state: State) -> bool:
        rt = state.get("runtime", {})
        if not isinstance(rt, dict):
            return False
        return bool(rt.get("context_builder_route_applied", False))

    def _apply_route_from_tool(state: State, payload: dict[str, Any]) -> None:
        rt = state.setdefault("runtime", {})
        if not isinstance(rt, dict):
            rt = {}
            state["runtime"] = rt

        node = str(payload.get("node") or "").strip().lower()
        status = str(payload.get("status") or "").strip().lower()
        raw_issues = payload.get("issues")
        issues: list[str] = []
        if isinstance(raw_issues, list):
            for issue in raw_issues:
                s = str(issue).strip()
                if s:
                    issues.append(s)

        handoff_note = payload.get("handoff_note")
        handoff_note_text = str(handoff_note).strip() if isinstance(handoff_note, str) else ""

        node_status = rt.setdefault("node_status", {})
        if not isinstance(node_status, dict):
            node_status = {}
            rt["node_status"] = node_status

        if status not in ALLOWED_ROUTE_STATUS:
            issues.append(f"invalid route status '{status}'")
            status = "blocked"

        if node not in ALLOWED_ROUTE_TARGETS:
            issues.append(f"invalid route target '{node}'")
            status = "blocked"

        node_status["context_builder"] = {
            "node": node,
            "status": status,
            "issues": issues,
            "handoff_note": handoff_note_text,
        }

        if node in ALLOWED_ROUTE_TARGETS:
            rt["context_builder_route_node"] = node
            rt["context_builder_route_applied"] = True
            rt["context_builder_status"] = status
            rt["context_builder_issues"] = issues
            if handoff_note_text:
                rt["context_builder_handoff_note"] = handoff_note_text

    def _build_invalid_output_feedback(
        state: State,
        last_tool: str | None,
        error_message: str,
    ) -> dict[str, Any]:
        _ = state
        _ = error_message
        return build_invalid_output_feedback_payload(
            allowed_actions=["tool_call", "route_node"],
            last_tool=last_tool,
            node_hint=(
                "Do not explain. Do not apologize. Do not summarize. "
                "If the current context already satisfies the turn, call route_node now. "
                "Otherwise call exactly one tool now."
            ),
        )

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

        if tool_name == "route_node":
            if isinstance(payload, dict) and payload.get("ok"):
                _apply_route_from_tool(state, payload)
            return

        entry = {
            "kind": "tool_result",
            "title": f"Tool result: {tool_name}",
            "records": as_records(payload),
        }
        replace_source_by_kind(ctx, kind="tool_result", entry=entry)

    def apply_handoff(state: State, obj: dict) -> bool:
        _ = state
        _ = obj
        raise RuntimeError("context_builder must hand off via route_node tool")

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
            stop_when=_route_done,
            invalid_output_retry_limit=2,
            build_invalid_output_feedback=_build_invalid_output_feedback,
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
