from __future__ import annotations

import json
from typing import Any, Callable, Optional, Sequence

from runtime.emitter import TurnEmitter
from runtime.providers.types import Message, ToolCall
from runtime.tool_loop import ToolSet, execute_tool_handler

from .primitives import safe_json_loads


def ensure_tool_transcript(state: dict, node_id: str) -> list[dict[str, Any]]:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt

    transcripts = rt.setdefault("tool_transcripts", {})
    if not isinstance(transcripts, dict):
        transcripts = {}
        rt["tool_transcripts"] = transcripts

    entries = transcripts.get(node_id)
    if not isinstance(entries, list):
        entries = []
        transcripts[node_id] = entries
    return entries


def reset_tool_transcript(state: dict, node_id: str) -> None:
    rt = state.setdefault("runtime", {})
    if not isinstance(rt, dict):
        rt = {}
        state["runtime"] = rt
    transcripts = rt.setdefault("tool_transcripts", {})
    if not isinstance(transcripts, dict):
        transcripts = {}
        rt["tool_transcripts"] = transcripts
    transcripts[node_id] = []


def filter_toolset(
    default_toolset: ToolSet,
    *,
    allowed: set[str],
    handler_wrappers: dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]] | None = None,
) -> ToolSet:
    defs = [tool_def for tool_def in default_toolset.defs if tool_def.name in allowed]
    handlers = {name: handler for name, handler in default_toolset.handlers.items() if name in allowed}
    if handler_wrappers:
        for tool_name, wrapper in handler_wrappers.items():
            if tool_name not in handlers:
                continue
            handlers[tool_name] = wrapper(handlers[tool_name])
    validators = None
    if default_toolset.validators:
        validators = {
            name: validator for name, validator in default_toolset.validators.items() if name in allowed
        }
    descriptors = {
        name: descriptor for name, descriptor in default_toolset.descriptors.items() if name in allowed
    }
    return ToolSet(
        defs=defs,
        handlers=handlers,
        validators=validators or None,
        descriptors=descriptors,
        approval_requester=default_toolset.approval_requester,
    )


def run_tools_mechanically(
    *,
    toolset: ToolSet,
    calls: Sequence[tuple[str, dict]],
    emitter: Optional[TurnEmitter] = None,
    node_id: Optional[str] = None,
    span_id: Optional[str] = None,
) -> list[Message]:
    """Execute tool handlers deterministically without a model tool_call."""
    out: list[Message] = []
    for idx, (name, args) in enumerate(calls, start=1):
        descriptor = toolset.descriptors.get(name)
        if name not in toolset.handlers:
            continue
        tool_call_id = f"prefill_{idx}"

        if emitter is not None:
            try:
                args_compact = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                args_compact = "{}"
            if len(args_compact) > 400:
                args_compact = args_compact[:400] + "…"
            emitter.emit(
                emitter.factory.log_line(
                    level="info",
                    logger="tool_loop",
                    message=f"[tool] call {name} args={args_compact}",
                    node_id=node_id,
                    span_id=span_id,
                    fields={"tool": name, "args": args, "mechanical": True, "index": idx},
                )
            )
            if node_id and span_id:
                emitter.tool_call(
                    node_id=node_id,
                    span_id=span_id,
                    tool_name=name,
                    tool_call_id=tool_call_id,
                    args=args,
                    step=idx,
                    tool_kind=descriptor.kind if descriptor is not None else None,
                    mcp_server_id=descriptor.server_id if descriptor is not None else None,
                    mcp_remote_name=descriptor.remote_name if descriptor is not None else None,
                )

        outcome = execute_tool_handler(
            tools=toolset,
            tool_name=name,
            args_obj=args,
            descriptor=descriptor,
            emitter=emitter,
            node_id=node_id,
            span_id=span_id,
            step=idx,
            tool_call_id=tool_call_id,
        )
        result_text = outcome.text

        if not outcome.ok and outcome.error is not None and emitter is not None:
            emitter.emit(
                emitter.factory.log_line(
                    level="error",
                    logger="tool_loop",
                    message=f"[tool] error {name}: {outcome.error}",
                    node_id=node_id,
                    span_id=span_id,
                    fields={"tool": name, "args": args, "mechanical": True, "error": outcome.error},
                )
            )
        if emitter is not None and node_id and span_id:
            emitter.tool_result(
                node_id=node_id,
                span_id=span_id,
                tool_name=name,
                tool_call_id=tool_call_id,
                result=outcome.payload,
                ok=outcome.ok,
                step=idx,
                error=outcome.error,
                tool_kind=descriptor.kind if descriptor is not None else None,
                mcp_server_id=descriptor.server_id if descriptor is not None else None,
                mcp_remote_name=descriptor.remote_name if descriptor is not None else None,
            )

        out.append(Message(role="tool", name=name, tool_call_id=tool_call_id, content=result_text))
    return out


def apply_world_update_tool_result(
    state: dict,
    *,
    node_id: str,
    tool_name: str,
    result_text: str,
    accepted_tool_name: str = "world_apply_ops",
) -> bool:
    if tool_name != accepted_tool_name:
        return False
    payload = safe_json_loads(result_text)
    if not isinstance(payload, dict) or not isinstance(payload.get("world"), dict):
        return True
    state["world"] = payload["world"]
    try:
        emitter = (state.get("runtime") or {}).get("emitter")
        if emitter is not None:
            emitter.world_update(
                node_id=node_id,
                span_id=None,
                world=state.get("world", {}) or {},
            )
    except Exception:
        pass
    return True


def execute_recovered_tool_call(
    *,
    recovered_tool_call: ToolCall,
    tools: ToolSet,
    emitter: TurnEmitter | None = None,
    node_id: str | None = None,
    span_id: str | None = None,
    step: int | None = None,
    on_tool_result: Optional[Callable[[str, str], bool | None]] = None,
    on_tool_executed: Optional[Callable[[dict[str, Any]], None]] = None,
) -> bool:
    """Execute a tool call recovered from assistant text using the normal tool path."""
    descriptor = tools.descriptors.get(recovered_tool_call.name)
    try:
        args_obj = json.loads(recovered_tool_call.arguments_json or "{}")
    except Exception as e:
        raise RuntimeError(f"Recovered tool arguments were not valid JSON: {e}") from e
    if not isinstance(args_obj, dict):
        raise RuntimeError("Recovered tool arguments must be a JSON object")

    tool_kind = descriptor.kind if descriptor is not None else None
    mcp_server_id = descriptor.server_id if descriptor is not None else None
    mcp_remote_name = descriptor.remote_name if descriptor is not None else None

    if emitter is not None and node_id and span_id:
        emitter.tool_call(
            node_id=node_id,
            span_id=span_id,
            tool_name=recovered_tool_call.name,
            tool_call_id=recovered_tool_call.id,
            args=args_obj,
            step=step,
            tool_kind=tool_kind,
            mcp_server_id=mcp_server_id,
            mcp_remote_name=mcp_remote_name,
        )
        emitter.emit(
            emitter.factory.log_line(
                level="warning",
                logger="tool_loop",
                message=f"[tool] recovered_from_text {recovered_tool_call.name}",
                node_id=node_id,
                span_id=span_id,
                fields={
                    "tool": recovered_tool_call.name,
                    "tool_call_id": recovered_tool_call.id,
                    "args": args_obj,
                    "step": step,
                    "recovered_from_text": True,
                },
            )
        )

    outcome = execute_tool_handler(
        tools=tools,
        tool_name=recovered_tool_call.name,
        args_obj=args_obj,
        descriptor=descriptor,
        emitter=emitter,
        node_id=node_id,
        span_id=span_id,
        step=step,
        tool_call_id=recovered_tool_call.id,
    )
    result_text = outcome.text

    if emitter is not None and node_id and span_id:
        emitter.tool_result(
            node_id=node_id,
            span_id=span_id,
            tool_name=recovered_tool_call.name,
            tool_call_id=recovered_tool_call.id,
            result=outcome.payload,
            ok=outcome.ok,
            step=step,
            error=outcome.error,
            tool_kind=tool_kind,
            mcp_server_id=mcp_server_id,
            mcp_remote_name=mcp_remote_name,
        )

    if on_tool_executed is not None:
        on_tool_executed(
            {
                "step": step,
                "tool_call_id": recovered_tool_call.id,
                "tool_name": recovered_tool_call.name,
                "tool_kind": tool_kind,
                "args": args_obj,
                "result": outcome.payload,
                "result_text": result_text,
                "ok": outcome.ok,
                "error": outcome.error,
                "mcp_server_id": mcp_server_id,
                "mcp_remote_name": mcp_remote_name,
                "recovered_from_text": True,
            }
        )

    if on_tool_result is not None:
        return bool(on_tool_result(recovered_tool_call.name, result_text))
    return False
