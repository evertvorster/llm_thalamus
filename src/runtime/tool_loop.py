from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Mapping, Optional, Sequence, Mapping as TMapping

from runtime.providers.base import LLMProvider
from runtime.providers.types import ChatRequest, Message, StreamEvent, ToolCall, ToolDef
from runtime.deps import _chat_params_from_mapping
from runtime.emitter import TurnEmitter
from runtime.tools.descriptor import ToolDescriptor
from runtime.tools.types import ToolApprovalRequest, ToolApprovalRequester, ToolHandler, ToolResult, ToolValidator


@dataclass(frozen=True)
class ToolSet:
    """
    Tools available to the model for this call.
    - defs: tool schemas sent to provider
    - handlers: deterministic executors keyed by tool name
    - descriptors: provider-neutral metadata keyed by public tool name
    """
    defs: Sequence[ToolDef]
    handlers: TMapping[str, ToolHandler]
    validators: TMapping[str, ToolValidator] | None = None
    descriptors: TMapping[str, ToolDescriptor] = field(default_factory=dict)
    approval_requester: ToolApprovalRequester | None = None


@dataclass(frozen=True)
class ToolExecutionOutcome:
    payload: Any
    text: str
    ok: bool
    error: str | None = None


def _parse_tool_args_json(raw: str) -> Any:
    try:
        obj = json.loads(raw) if raw else {}
    except Exception as e:
        raise RuntimeError(f"Tool arguments were not valid JSON: {e}: {raw!r}") from e

    if isinstance(obj, str):
        try:
            obj2 = json.loads(obj)
            obj = obj2
        except Exception:
            pass

    return obj


def _normalize_tool_result(result: ToolResult) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        raise RuntimeError(f"Tool result was not JSON-serializable: {e}: {type(result).__name__}") from e


def _normalize_tool_result_event_payload(result: ToolResult) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return result
    return result


def _validate_tool_result(
    *,
    tool_name: str,
    result: ToolResult,
    validators: Optional[TMapping[str, ToolValidator]],
) -> None:
    if not validators:
        return
    v = validators.get(tool_name)
    if v is None:
        return

    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            parsed = result
        v(parsed)
        return

    v(result)


def _emit_llm_request(
    *,
    emitter: TurnEmitter | None,
    provider: LLMProvider,
    req: ChatRequest,
    node_id: str | None,
    span_id: str | None,
    kind: str,
    step: int | None = None,
) -> None:
    if emitter is None or not node_id or not span_id:
        return

    build = getattr(provider, "build_chat_payload", None)
    if not callable(build):
        return

    try:
        payload = build(req)
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return

    curl = None
    build_curl = getattr(provider, "build_chat_curl", None)
    if callable(build_curl):
        try:
            curl = build_curl(payload)
        except Exception:
            curl = None

    emitter.emit(
        emitter.factory.llm_request(
            node_id=node_id,
            span_id=span_id,
            provider=str(getattr(provider, "provider_name", lambda: "unknown")()),
            request=payload,
            curl=curl,
        )
    )


def _tool_denied_outcome(*, approval_mode: str, message: str) -> ToolExecutionOutcome:
    payload = {
        "ok": False,
        "error": {
            "code": "tool_denied",
            "message": message,
            "approval": approval_mode,
        },
    }
    return ToolExecutionOutcome(
        payload=payload,
        text=json.dumps(payload, ensure_ascii=False),
        ok=False,
        error=message,
    )


def _request_tool_approval(
    *,
    tools: ToolSet,
    descriptor: ToolDescriptor | None,
    tool_name: str,
    args: dict[str, Any],
    node_id: str | None,
    span_id: str | None,
    step: int | None,
    tool_call_id: str | None,
    emitter: TurnEmitter | None,
) -> ToolExecutionOutcome | None:
    mode = descriptor.approval_mode if descriptor is not None else "auto"
    if mode == "auto":
        return None

    if mode == "deny":
        if emitter is not None:
            emitter.emit(
                emitter.factory.log_line(
                    level="warning",
                    logger="tool_loop",
                    message=f"[tool] denied by policy {tool_name}",
                    node_id=node_id,
                    span_id=span_id,
                    fields={"tool": tool_name, "approval": mode, "args": args},
                )
            )
        return _tool_denied_outcome(
            approval_mode=mode,
            message=f"Tool '{tool_name}' is denied by policy.",
        )

    requester = tools.approval_requester
    if requester is None:
        return _tool_denied_outcome(
            approval_mode=mode,
            message=f"Tool '{tool_name}' requires approval, but no approval requester is configured.",
        )

    if emitter is not None:
        emitter.emit(
            emitter.factory.log_line(
                level="info",
                logger="tool_loop",
                message=f"[tool] approval requested {tool_name}",
                node_id=node_id,
                span_id=span_id,
                fields={"tool": tool_name, "approval": mode, "args": args},
            )
        )

    try:
        approved = bool(
            requester(
                ToolApprovalRequest(
                    tool_name=tool_name,
                    args=args,
                    tool_kind=descriptor.kind if descriptor is not None else None,
                    description=descriptor.description if descriptor is not None else "",
                    node_id=node_id,
                    span_id=span_id,
                    step=step,
                    tool_call_id=tool_call_id,
                    mcp_server_id=descriptor.server_id if descriptor is not None else None,
                    mcp_remote_name=descriptor.remote_name if descriptor is not None else None,
                )
            )
        )
    except Exception as e:
        return _tool_denied_outcome(
            approval_mode=mode,
            message=f"Tool approval failed for '{tool_name}': {e}",
        )

    if approved:
        if emitter is not None:
            emitter.emit(
                emitter.factory.log_line(
                    level="info",
                    logger="tool_loop",
                    message=f"[tool] approved {tool_name}",
                    node_id=node_id,
                    span_id=span_id,
                    fields={"tool": tool_name, "approval": mode, "args": args},
                )
            )
        return None

    if emitter is not None:
        emitter.emit(
            emitter.factory.log_line(
                level="warning",
                logger="tool_loop",
                message=f"[tool] approval denied {tool_name}",
                node_id=node_id,
                span_id=span_id,
                fields={"tool": tool_name, "approval": mode, "args": args},
            )
        )
    return _tool_denied_outcome(
        approval_mode=mode,
        message=f"Tool '{tool_name}' was denied at approval time.",
    )


def execute_tool_handler(
    *,
    tools: ToolSet,
    tool_name: str,
    args_obj: dict[str, Any],
    descriptor: ToolDescriptor | None,
    emitter: TurnEmitter | None = None,
    node_id: str | None = None,
    span_id: str | None = None,
    step: int | None = None,
    tool_call_id: str | None = None,
) -> ToolExecutionOutcome:
    handler = tools.handlers.get(tool_name)
    if handler is None:
        raise RuntimeError(
            f"Model requested unknown tool '{tool_name}'. "
            f"Available: {sorted(tools.handlers.keys())}"
        )

    approval_outcome = _request_tool_approval(
        tools=tools,
        descriptor=descriptor,
        tool_name=tool_name,
        args=args_obj,
        node_id=node_id,
        span_id=span_id,
        step=step,
        tool_call_id=tool_call_id,
        emitter=emitter,
    )
    if approval_outcome is not None:
        return approval_outcome

    try:
        tool_result = handler(args_obj)
        _validate_tool_result(tool_name=tool_name, result=tool_result, validators=tools.validators)
        payload = _normalize_tool_result_event_payload(tool_result)
        text = _normalize_tool_result(tool_result)
        return ToolExecutionOutcome(payload=payload, text=text, ok=True, error=None)
    except Exception as e:
        payload = {"ok": False, "error": {"message": str(e)}}
        return ToolExecutionOutcome(
            payload=payload,
            text=json.dumps(payload, ensure_ascii=False),
            ok=False,
            error=str(e),
        )


def _stream_provider_once(
    *,
    provider: LLMProvider,
    req: ChatRequest,
) -> tuple[list[ToolCall], str, Iterator[StreamEvent]]:
    tool_calls: List[ToolCall] = []
    assistant_parts: List[str] = []

    def gen() -> Iterator[StreamEvent]:
        for ev in provider.chat_stream(req):
            if ev.type == "tool_call" and ev.tool_call:
                tool_calls.append(ev.tool_call)
                yield ev
                continue

            if ev.type == "delta_text" and ev.text:
                assistant_parts.append(ev.text)

            if ev.type == "done":
                break

            yield ev

    return tool_calls, "".join(assistant_parts), gen()


def chat_stream(
    *,
    provider: LLMProvider,
    model: str,
    messages: List[Message],
    params: Mapping[str, Any],
    response_format: Any,
    tools: Optional[ToolSet],
    max_steps: int,
    emitter: Optional[TurnEmitter] = None,
    node_id: Optional[str] = None,
    span_id: Optional[str] = None,
    on_tool_result: Optional[Callable[[str, str], bool | None]] = None,
) -> Iterator[StreamEvent]:
    if max_steps <= 0:
        raise RuntimeError(f"max_steps must be > 0 (got {max_steps})")

    if tools is None:
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=None,
            response_format=response_format,
            params=_chat_params_from_mapping(params),
            stream=True,
        )
        _emit_llm_request(emitter=emitter, provider=provider, req=req, node_id=node_id, span_id=span_id, kind="chat", step=None)
        for ev in provider.chat_stream(req):
            if ev.type == "done":
                break
            yield ev
        yield StreamEvent(type="done")
        return

    for step in range(1, max_steps + 1):
        tool_req = ChatRequest(
            model=model,
            messages=messages,
            tools=tools.defs,
            response_format=None,
            params=_chat_params_from_mapping(params),
            stream=True,
        )

        _emit_llm_request(emitter=emitter, provider=provider, req=tool_req, node_id=node_id, span_id=span_id, kind="tool_round", step=step)

        tool_calls, assistant_text, passthrough = _stream_provider_once(provider=provider, req=tool_req)
        for ev in passthrough:
            yield ev

        if not tool_calls:
            if response_format is None:
                yield StreamEvent(type="done")
                return

            final_req = ChatRequest(
                model=model,
                messages=messages,
                tools=None,
                response_format=response_format,
                params=_chat_params_from_mapping(params),
                stream=True,
            )
            _emit_llm_request(emitter=emitter, provider=provider, req=final_req, node_id=node_id, span_id=span_id, kind="final_format", step=step)
            for ev in provider.chat_stream(final_req):
                if ev.type == "done":
                    break
                yield ev
            yield StreamEvent(type="done")
            return

        messages.append(
            Message(
                role="assistant",
                content=assistant_text,
                tool_calls=list(tool_calls),
            )
        )

        for tc in tool_calls:
            descriptor = tools.descriptors.get(tc.name)
            args_obj = _parse_tool_args_json(tc.arguments_json)
            if not isinstance(args_obj, dict):
                raise RuntimeError(f"Tool arguments must be a JSON object (got {type(args_obj).__name__})")

            tool_kind = descriptor.kind if descriptor is not None else None
            mcp_server_id = descriptor.server_id if descriptor is not None else None
            mcp_remote_name = descriptor.remote_name if descriptor is not None else None

            if emitter is not None and node_id and span_id:
                emitter.tool_call(
                    node_id=node_id,
                    span_id=span_id,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    args=args_obj,
                    step=step,
                    tool_kind=tool_kind,
                    mcp_server_id=mcp_server_id,
                    mcp_remote_name=mcp_remote_name,
                )

            if emitter is not None:
                try:
                    args_compact = json.dumps(args_obj, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    args_compact = tc.arguments_json
                if len(args_compact) > 400:
                    args_compact = args_compact[:400] + "…"

                fields: dict[str, Any] = {
                    "tool": tc.name,
                    "tool_call_id": tc.id,
                    "args": args_obj,
                    "step": step,
                }
                if descriptor is not None:
                    fields.update(
                        {
                            "tool_kind": tool_kind,
                            "mcp_server_id": mcp_server_id,
                            "mcp_remote_name": mcp_remote_name,
                        }
                    )

                emitter.emit(
                    emitter.factory.log_line(
                        level="info",
                        logger="tool_loop",
                        message=f"[tool] call {tc.name} args={args_compact}",
                        node_id=node_id,
                        span_id=span_id,
                        fields=fields,
                    )
                )
            tool_result_payload: Any
            tool_result_ok = True
            tool_result_error: str | None = None
            outcome = execute_tool_handler(
                tools=tools,
                tool_name=tc.name,
                args_obj=args_obj,
                descriptor=descriptor,
                emitter=emitter,
                node_id=node_id,
                span_id=span_id,
                step=step,
                tool_call_id=tc.id,
            )
            tool_result_ok = outcome.ok
            tool_result_error = outcome.error
            tool_result_payload = outcome.payload
            result_text = outcome.text

            if (not tool_result_ok) and tool_result_error is not None and emitter is not None:
                fields = {
                    "tool": tc.name,
                    "tool_call_id": tc.id,
                    "args": args_obj,
                    "step": step,
                    "error": tool_result_error,
                }
                if descriptor is not None:
                    fields.update(
                        {
                            "tool_kind": tool_kind,
                            "mcp_server_id": mcp_server_id,
                            "mcp_remote_name": mcp_remote_name,
                        }
                    )
                emitter.emit(
                    emitter.factory.log_line(
                        level="error",
                        logger="tool_loop",
                        message=f"[tool] error {tc.name}: {tool_result_error}",
                        node_id=node_id,
                        span_id=span_id,
                        fields=fields,
                    )
                )

            if emitter is not None and node_id and span_id:
                emitter.tool_result(
                    node_id=node_id,
                    span_id=span_id,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    result=tool_result_payload,
                    ok=tool_result_ok,
                    step=step,
                    error=tool_result_error,
                    tool_kind=tool_kind,
                    mcp_server_id=mcp_server_id,
                    mcp_remote_name=mcp_remote_name,
                )

            yield StreamEvent(
                type="tool_result",
                text=result_text,
            )

            messages.append(
                Message(
                    role="tool",
                    name=tc.name,
                    tool_call_id=tc.id,
                    content=result_text,
                )
            )

            if on_tool_result is not None:
                should_stop = on_tool_result(tc.name, result_text)
                if should_stop:
                    yield StreamEvent(type="done")
                    return

    raise RuntimeError(
        f"Tool loop exceeded max_steps={max_steps} (model kept calling tools)."
    )
