from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.nodes_common.primitives import append_node_trace, get_emitter
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State

NODE_ID = "llm.reflect_memory"
GROUP = "mechanical"
LABEL = "Reflect Memory"
ROLE_KEY = "mechanical"
RUNTIME_COMPLETE_KEY = "reflect_memory_complete"
RUNTIME_STATUS_KEY = "reflect_memory_status"
RUNTIME_RESULT_KEY = "reflect_memory_result"
RUNTIME_STORED_COUNT_KEY = "reflect_memory_stored_count"
NODE_STATUS_KEY = "reflect_memory"
MEMORY_SERVER_ID = "mempalace"
MEMORY_TOOL_NAME = "mempalace_add_drawer"
DEFAULT_WING = "dora"
DEFAULT_ROOM = "sessions"


def _current_exchange(state: State) -> tuple[str, str]:
    user_text = str((state.get("task") or {}).get("user_text") or "").strip()
    assistant_text = str((state.get("final") or {}).get("answer") or "").strip()
    return user_text, assistant_text


def _conversation_drawer_content(state: State) -> str:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        rt = {}
    user_text, assistant_text = _current_exchange(state)
    lines = [
        "type: conversation_exchange",
        f"turn_id: {str(rt.get('turn_id') or '').strip()}",
        f"timestamp: {str(rt.get('now_iso') or '').strip()}",
        "",
        "human:",
        user_text,
        "",
        "assistant:",
        assistant_text,
    ]
    return "\n".join(lines).strip() + "\n"


def _drawer_args(state: State) -> dict[str, Any]:
    rt = state.get("runtime") or {}
    if not isinstance(rt, dict):
        rt = {}
    turn_id = str(rt.get("turn_id") or "turn").strip() or "turn"
    return {
        "wing": DEFAULT_WING,
        "room": DEFAULT_ROOM,
        "content": _conversation_drawer_content(state),
        "source_file": f"llm_thalamus/{turn_id}.md",
        "added_by": "llm_thalamus",
    }


def _complete_memory(
    state: State,
    *,
    stored: list[dict[str, Any]] | None = None,
    notes: str = "",
    issues: list[str] | None = None,
) -> None:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt

    node_status = rt.setdefault("node_status", {})
    if not isinstance(node_status, dict):
        node_status = {}
        rt["node_status"] = node_status

    out_stored = list(stored or [])
    out_issues = [str(x).strip() for x in (issues or []) if str(x).strip()]
    out_notes = notes.strip()
    result = {
        "complete": True,
        "stored": out_stored,
        "stored_count": len(out_stored),
        "issues": out_issues,
        "notes": out_notes,
    }
    node_status[NODE_STATUS_KEY] = result
    rt[RUNTIME_COMPLETE_KEY] = True
    rt[RUNTIME_STATUS_KEY] = "ok" if not out_issues else "skipped"
    rt[RUNTIME_STORED_COUNT_KEY] = len(out_stored)
    rt[RUNTIME_RESULT_KEY] = result


def _mempalace_available(services: RuntimeServices) -> bool:
    resources = services.tool_resources
    if resources.mcp is None or MEMORY_SERVER_ID not in resources.mcp.server_ids():
        return False
    catalog = dict(resources.mcp_tool_catalog or {})
    specs = catalog.get(MEMORY_SERVER_ID, [])
    return any(isinstance(spec, dict) and spec.get("name") == MEMORY_TOOL_NAME for spec in specs)


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    _ = deps

    def node(state: State) -> State:
        append_node_trace(state, NODE_ID)
        emitter = get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)
        try:
            user_text, assistant_text = _current_exchange(state)
            if not user_text or not assistant_text:
                _complete_memory(
                    state,
                    notes="Conversation exchange not stored because user or assistant text was empty.",
                    issues=["empty_exchange"],
                )
                span.end_ok()
                return state

            if not _mempalace_available(services):
                _complete_memory(
                    state,
                    notes="Conversation exchange not stored because MemPalace MCP add-drawer is unavailable.",
                    issues=["mempalace_unavailable"],
                )
                span.end_ok()
                return state

            args = _drawer_args(state)
            span_id = getattr(span, "span_id", None)
            try:
                args_compact = json.dumps({**args, "content": "[verbatim exchange redacted from log]"}, ensure_ascii=False, separators=(",", ":"))
                emitter.emit(
                    emitter.factory.log_line(
                        level="info",
                        logger="reflect_memory",
                        message=f"[tool] call {MEMORY_TOOL_NAME} args={args_compact}",
                        node_id=NODE_ID,
                        span_id=span_id,
                        fields={"tool": MEMORY_TOOL_NAME, "args": {**args, "content": "[redacted]"}, "mechanical": True},
                    )
                )
                emitter.tool_call(
                    node_id=NODE_ID,
                    span_id=span_id,
                    tool_name=MEMORY_TOOL_NAME,
                    tool_call_id="reflect_memory_1",
                    args=args,
                    step=1,
                    tool_kind="mcp",
                    mcp_server_id=MEMORY_SERVER_ID,
                    mcp_remote_name=MEMORY_TOOL_NAME,
                )
            except Exception:
                pass

            assert services.tool_resources.mcp is not None
            result = services.tool_resources.mcp.call_tool(
                MEMORY_SERVER_ID,
                name=MEMORY_TOOL_NAME,
                arguments=args,
                request_id=30,
            )
            stored_record = {
                "wing": args["wing"],
                "room": args["room"],
                "source_file": args["source_file"],
                "result": result.raw,
            }
            try:
                emitter.tool_result(
                    node_id=NODE_ID,
                    span_id=span_id,
                    tool_name=MEMORY_TOOL_NAME,
                    tool_call_id="reflect_memory_1",
                    result=result.raw,
                    ok=result.ok,
                    step=1,
                    error=result.error,
                    tool_kind="mcp",
                    mcp_server_id=MEMORY_SERVER_ID,
                    mcp_remote_name=MEMORY_TOOL_NAME,
                )
            except Exception:
                pass

            if not result.ok:
                _complete_memory(
                    state,
                    notes="MemPalace add-drawer call failed.",
                    issues=[str(result.error or "mempalace_add_failed")],
                )
            else:
                _complete_memory(state, stored=[stored_record], notes="Stored verbatim conversation exchange in MemPalace.")
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
