from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Mapping, Optional, Sequence, Mapping as TMapping

from runtime.providers.base import LLMProvider
from runtime.providers.types import ChatRequest, Message, StreamEvent, ToolCall, ToolDef
from runtime.deps import _chat_params_from_mapping
from runtime.emitter import TurnEmitter


ToolArgs = dict[str, Any]
ToolResult = Any  # must be JSON-serializable or a plain string
ToolHandler = Callable[[ToolArgs], ToolResult]  # input: parsed args object
ToolValidator = Callable[[ToolResult], None]


@dataclass(frozen=True)
class ToolSet:
    """
    Tools available to the model for this call.
    - defs: tool schemas sent to provider
    - handlers: deterministic executors keyed by tool name
    """
    defs: Sequence[ToolDef]
    handlers: TMapping[str, ToolHandler]
    validators: TMapping[str, ToolValidator] | None = None


def _parse_tool_args_json(raw: str) -> Any:
    """
    Tool args arrive as a JSON string (provider contract).
    We validate JSON here to fail loudly and early.
    """
    try:
        return json.loads(raw) if raw else {}
    except Exception as e:
        raise RuntimeError(f"Tool arguments were not valid JSON: {e}: {raw!r}") from e


def _normalize_tool_result(result: ToolResult) -> str:
    """Normalize a tool handler return value into a string for tool message injection.

    - If the handler returns a string, it is passed through (assumed already formatted).
    - Otherwise, we JSON-serialize it (must be JSON-serializable).
    """
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
    """Apply an optional per-tool validator.

    Validators should raise a ValueError/RuntimeError with a clear message if invalid.
    """
    if not validators:
        return
    v = validators.get(tool_name)
    if v is None:
        return

    # If handler returned a JSON string, validate against the parsed object (when possible),
    # but keep the original string for injection.
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            parsed = result
        v(parsed)
        return

    v(result)


def _stream_provider_once(
    *,
    provider: LLMProvider,
    req: ChatRequest,
) -> tuple[list[ToolCall], Iterator[StreamEvent]]:
    """
    Run one provider stream and:
    - yield-through all events (except provider 'done')
    - collect tool_calls (from StreamEvent(type="tool_call"))
    Returns (tool_calls, passthrough_iterator)
    """
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
) -> Iterator[StreamEvent]:
    """
    Centralized deterministic tool loop (streaming-only).

    Option A behavior:
    - While tools are enabled, DO NOT force response_format (lets tool_calls happen).
    - After tools are done (no tool_calls), optionally run a final formatting pass
      with response_format enforced and tools disabled (to satisfy JSON-only prompts).

    Nodes MUST NOT execute tools themselves.
    """
    if max_steps <= 0:
        raise RuntimeError(f"max_steps must be > 0 (got {max_steps})")

    # If no tools are enabled, this becomes a simple pass-through stream.
    if tools is None:
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=None,
            response_format=response_format,
            params=_chat_params_from_mapping(params),
            stream=True,
        )
        for ev in provider.chat_stream(req):
            if ev.type == "done":
                break
            yield ev
        yield StreamEvent(type="done")
        return

    # Tool-capable loop: tool rounds first (NO response_format), then optional final formatting pass.
    for step in range(1, max_steps + 1):
        # Tool round: allow tool_calls by not forcing response_format.
        tool_req = ChatRequest(
            model=model,
            messages=messages,
            tools=tools.defs,
            response_format=None,  # critical: don't force JSON while tools are available
            params=_chat_params_from_mapping(params),
            stream=True,
        )

        tool_calls, passthrough = _stream_provider_once(provider=provider, req=tool_req)
        for ev in passthrough:
            yield ev

        # If no tool calls, tools are done. Now optionally enforce response_format in a final pass.
        if not tool_calls:
            if response_format is None:
                yield StreamEvent(type="done")
                return

            # Final formatting pass: enforce JSON-only output, and disable tools to avoid re-entering tool loop.
            final_req = ChatRequest(
                model=model,
                messages=messages,
                tools=None,
                response_format=response_format,
                params=_chat_params_from_mapping(params),
                stream=True,
            )
            for ev in provider.chat_stream(final_req):
                if ev.type == "done":
                    break
                yield ev
            yield StreamEvent(type="done")
            return

        # Execute each tool call deterministically and append results.
        for tc in tool_calls:
            handler = tools.handlers.get(tc.name)
            if handler is None:
                raise RuntimeError(
                    f"Model requested unknown tool '{tc.name}'. "
                    f"Available: {sorted(tools.handlers.keys())}"
                )

            # Validate args JSON (fail loudly if not JSON).
            args_obj = _parse_tool_args_json(tc.arguments_json)
            if not isinstance(args_obj, dict):
                raise RuntimeError(f"Tool arguments must be a JSON object (got {type(args_obj).__name__})")


            # Emit a compact tool-call trace line into the thalamus log.
            # This confirms the tool loop is active and shows deterministic parameters.
            if emitter is not None:
                try:
                    args_compact = json.dumps(args_obj, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    args_compact = tc.arguments_json
                if len(args_compact) > 400:
                    args_compact = args_compact[:400] + "…"
                emitter.emit(
                    emitter.factory.log_line(
                        level="info",
                        logger="tool_loop",
                        message=f"[tool] call {tc.name} args={args_compact}",
                        node_id=node_id,
                        span_id=span_id,
                        fields={
                            "tool": tc.name,
                            "tool_call_id": tc.id,
                            "args": args_obj,
                            "step": step,
                        },
                    )
                )
            try:
                tool_result = handler(args_obj)
                _validate_tool_result(tool_name=tc.name, result=tool_result, validators=tools.validators)
                result_text = _normalize_tool_result(tool_result)

            except Exception as e:
                # Don't kill the node/turn on tool errors; surface the error to logs and to the model.
                if emitter is not None:
                    emitter.emit(
                        emitter.factory.log_line(
                            level="error",
                            logger="tool_loop",
                            message=f"[tool] error {tc.name}: {e}",
                            node_id=node_id,
                            span_id=span_id,
                            fields={
                                "tool": tc.name,
                                "tool_call_id": tc.id,
                                "args": args_obj,
                                "step": step,
                                "error": str(e),
                            },
                        )
                    )
                result_text = json.dumps(
                    {"ok": False, "error": {"message": str(e)}},
                    ensure_ascii=False,
                )

            # Forward a tool_result event for UI/diagnostics (optional consumption).
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

    raise RuntimeError(
        f"Tool loop exceeded max_steps={max_steps} (model kept calling tools)."
    )