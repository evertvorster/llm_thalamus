from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Mapping, Optional, Sequence, Mapping as TMapping

from runtime.providers.base import LLMProvider
from runtime.providers.types import ChatRequest, Message, StreamEvent, ToolCall, ToolDef
from runtime.deps import _chat_params_from_mapping


ToolHandler = Callable[[str], str]  # input: raw arguments_json; output: tool result string


@dataclass(frozen=True)
class ToolSet:
    """
    Tools available to the model for this call.
    - defs: tool schemas sent to provider
    - handlers: deterministic executors keyed by tool name
    """
    defs: Sequence[ToolDef]
    handlers: TMapping[str, ToolHandler]


def _parse_tool_args_json(raw: str) -> Any:
    """
    Tool args arrive as a JSON string (provider contract).
    We validate JSON here to fail loudly and early.
    """
    try:
        return json.loads(raw) if raw else {}
    except Exception as e:
        raise RuntimeError(f"Tool arguments were not valid JSON: {e}: {raw!r}") from e


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
            _parse_tool_args_json(tc.arguments_json)

            result_text = handler(tc.arguments_json)

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
