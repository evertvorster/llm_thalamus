from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

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
    handlers: Mapping[str, ToolHandler]


def _parse_tool_args_json(raw: str) -> Any:
    """
    Tool args arrive as a JSON string (provider contract).
    We validate JSON here to fail loudly and early.
    """
    try:
        return json.loads(raw) if raw else {}
    except Exception as e:
        raise RuntimeError(f"Tool arguments were not valid JSON: {e}: {raw!r}") from e


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

    - Calls provider.chat_stream()
    - Streams delta_text / delta_thinking / usage out to the caller
    - Captures tool_call events
    - Executes tools deterministically
    - Appends tool results as Message(role="tool", ...)
    - Re-calls provider with appended tool results
    - Yields a single final StreamEvent(type="done") only when the loop finishes

    Nodes MUST NOT execute tools themselves.
    Nodes MAY ignore non-text events safely.

    Notes:
    - We forward provider events while also collecting tool calls.
    - We do NOT yield provider 'done' for intermediate rounds; only once at the end.
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

    # Tool-capable loop.
    for step in range(1, max_steps + 1):
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=tools.defs,
            response_format=response_format,
            params=_chat_params_from_mapping(params),
            stream=True,
        )

        tool_calls: List[ToolCall] = []

        # Stream provider events, collect tool calls.
        for ev in provider.chat_stream(req):
            if ev.type == "tool_call" and ev.tool_call:
                tool_calls.append(ev.tool_call)
                # Forward to caller for UI/diagnostics (node can ignore)
                yield ev
                continue

            if ev.type == "done":
                break

            # Forward everything else (delta_text, delta_thinking, usage, error)
            yield ev

        # If no tool calls, we’re done.
        if not tool_calls:
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
