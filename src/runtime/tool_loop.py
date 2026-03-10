from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Mapping, Optional, Sequence, Mapping as TMapping

from runtime.providers.base import LLMProvider
from runtime.providers.types import ChatRequest, Message, StreamEvent, ToolCall, ToolDef
from runtime.deps import _chat_params_from_mapping
from runtime.emitter import TurnEmitter
from runtime.tools.descriptor import ToolDescriptor
from runtime.tools.types import ToolHandler, ToolResult, ToolValidator


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


def _stream_provider_once(
    *,
    provider: LLMProvider,
    req: ChatRequest,
) -> tuple[list[ToolCall], Iterator[StreamEvent]]:
    tool_calls: List[ToolCall] = []

    def gen() -> Iterator[StreamEvent]:
        for ev in provider.chat_stream(req):
            if ev.type == "tool_call" and ev.tool_call:
                tool_calls.append(ev.tool_call)
                yield ev
                continue

            if ev.type == "done":
                break

            yield ev

    return tool_calls, gen()


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
    rebuild_messages: Optional[Callable[[], List[Message]]] = None,
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

        tool_calls, passthrough = _stream_provider_once(provider=provider, req=tool_req)
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

        restart_with_fresh_messages = False
        for tc in tool_calls:
            handler = tools.handlers.get(tc.name)
            if handler is None:
                raise RuntimeError(
                    f"Model requested unknown tool '{tc.name}'. "
                    f"Available: {sorted(tools.handlers.keys())}"
                )

            descriptor = tools.descriptors.get(tc.name)
            args_obj = _parse_tool_args_json(tc.arguments_json)
            if not isinstance(args_obj, dict):
                raise RuntimeError(f"Tool arguments must be a JSON object (got {type(args_obj).__name__})")

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
                            "tool_kind": descriptor.kind,
                            "mcp_server_id": descriptor.server_id,
                            "mcp_remote_name": descriptor.remote_name,
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
            try:
                tool_result = handler(args_obj)
                _validate_tool_result(tool_name=tc.name, result=tool_result, validators=tools.validators)
                result_text = _normalize_tool_result(tool_result)

            except Exception as e:
                if emitter is not None:
                    fields = {
                        "tool": tc.name,
                        "tool_call_id": tc.id,
                        "args": args_obj,
                        "step": step,
                        "error": str(e),
                    }
                    if descriptor is not None:
                        fields.update(
                            {
                                "tool_kind": descriptor.kind,
                                "mcp_server_id": descriptor.server_id,
                                "mcp_remote_name": descriptor.remote_name,
                            }
                        )
                    emitter.emit(
                        emitter.factory.log_line(
                            level="error",
                            logger="tool_loop",
                            message=f"[tool] error {tc.name}: {e}",
                            node_id=node_id,
                            span_id=span_id,
                            fields=fields,
                        )
                    )
                result_text = json.dumps(
                    {"ok": False, "error": {"message": str(e)}},
                    ensure_ascii=False,
                )

            yield StreamEvent(
                type="tool_result",
                text=result_text,
            )

            if on_tool_result is not None:
                should_stop = on_tool_result(tc.name, result_text)
                if should_stop:
                    yield StreamEvent(type="done")
                    return

            if rebuild_messages is not None:
                messages = rebuild_messages()
                restart_with_fresh_messages = True
                break

            status_payload = {"ok": True}
            try:
                parsed = json.loads(result_text)
                if isinstance(parsed, dict):
                    status_payload = {"ok": bool(parsed.get("ok", True))}
                    if "returned" in parsed:
                        status_payload["returned"] = parsed["returned"]
            except Exception:
                pass

            messages.append(
                Message(
                    role="tool",
                    name=tc.name,
                    tool_call_id=tc.id,
                    content=json.dumps(status_payload, ensure_ascii=False),
                )
            )

        if restart_with_fresh_messages:
            continue

    raise RuntimeError(
        f"Tool loop exceeded max_steps={max_steps} (model kept calling tools)."
    )
