# src/runtime/nodes/<group>_<name>.py  (template)
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional

from runtime.deps import Deps, _chat_params_from_mapping
from runtime.prompting import render_tokens
from runtime.providers.types import ChatRequest, Message, StreamEvent, ToolCall, ToolDef
from runtime.registry import NodeSpec, register
from runtime.state import State


# ---- Node metadata (used by registry / UI / manifests) ----

NODE_ID = "<group>.<name>"          # e.g. "llm.reflect" or "mech.build_context"
GROUP = "<group>"                   # e.g. "llm" | "mech"
LABEL = "<Human label>"             # e.g. "Reflect", "Build Context"
PROMPT_NAME = "<prompt_name>"       # e.g. "runtime_reflect" (resources/prompts/runtime_reflect.txt)

# Which role config / model mapping key to use in config (llm.langgraph_nodes / llm.role_params / llm.role_response_format)
ROLE_KEY = "<role_key>"             # e.g. "reflect" | "episode_sql" | "final" | "router"


# ---- Optional tools wiring (this template *exercises* Ollama tools) ----
#
# You will supply TOOL_DEFS (schema) and TOOL_HANDLERS (implementation) per node.
#
# Central tool loop will eventually live elsewhere. For now, this template includes a deterministic loop skeleton
# so every new node has the “full Ollama surface area” available immediately.
#

ToolHandler = Callable[[str], str]  # input is raw JSON string args; output is raw string (or JSON string)


@dataclass(frozen=True)
class ToolSpec:
    defs: List[ToolDef]
    handlers: Dict[str, ToolHandler]


def _append_log(state: State, kind: str, text: str) -> None:
    """
    Unifies node -> runner streaming logs.
    You already use _runtime_logs elsewhere; keep it consistent.
    """
    buf = state.setdefault("_runtime_logs", [])
    buf.append(text)


def _emit_node_event(state: State, *, phase: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Minimal structured event (optional).
    Keep it small; the UI can later render these in a sidebar.
    """
    ev = {
        "type": "node_event",
        "node_id": NODE_ID,
        "group": GROUP,
        "phase": phase,  # "start" | "end" | "error" | "progress"
        "msg": msg,
    }
    if data:
        ev["data"] = data
    state.setdefault("_runtime_events", []).append(ev)


def _collect_stream_text(events: Iterator[StreamEvent], state: State) -> str:
    """
    Collect assistant delta_text into a final string.
    Also forwards delta_text to the UI via _runtime_logs for live streaming.

    Thinking:
      Ollama doesn’t standardize a thinking stream field, but some providers/models can emit it.
      We pass it through if present.
    """
    parts: List[str] = []

    for ev in events:
        if ev.type == "delta_text" and ev.text:
            _append_log(state, "text", ev.text)
            parts.append(ev.text)

        elif ev.type == "delta_thinking" and ev.text:
            # Best-effort: some backends may emit this (your UI already shows thinking logs).
            _append_log(state, "thinking", ev.text)

        elif ev.type == "error":
            raise RuntimeError(ev.error or "LLM provider error")

        elif ev.type == "done":
            break

    return "".join(parts)


def _collect_tool_calls(events: Iterator[StreamEvent]) -> List[ToolCall]:
    calls: List[ToolCall] = []
    for ev in events:
        if ev.type == "tool_call" and ev.tool_call:
            calls.append(ev.tool_call)
        elif ev.type == "error":
            raise RuntimeError(ev.error or "LLM provider error")
        elif ev.type == "done":
            break
    return calls


def _run_tool_loop(
    *,
    deps: Deps,
    state: State,
    model: str,
    params: Mapping[str, Any],
    response_format: Any,
    messages: List[Message],
    tools: Optional[ToolSpec],
    max_steps: int,
) -> str:
    """
    Deterministic tool loop skeleton.

    IMPORTANT insight:
      “Pausing” is not freezing. We abort the current stream and start a new call with appended tool results.

    This template supports:
      - tool defs sent on every call
      - tool calls returned by model
      - tool execution locally (handlers)
      - appending tool results as Message(role="tool", ...)

    Later:
      Replace this entire function with your centralized tool loop module.
    """
    if tools is None:
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=None,
            response_format=response_format,
            params=_chat_params_from_mapping(params),
            stream=True,
        )
        return _collect_stream_text(deps.provider.chat_stream(req), state)

    # Tool-capable loop
    for step in range(max_steps):
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=tools.defs,
            response_format=response_format,
            params=_chat_params_from_mapping(params),
            stream=True,
        )

        # First pass: gather both text (for UI) and tool calls
        # We do a single stream iteration and:
        #  - forward text to UI as it arrives
        #  - collect tool calls if they appear
        # This keeps the UX streaming-friendly even during tool loops.
        tool_calls: List[ToolCall] = []
        text_parts: List[str] = []

        for ev in deps.provider.chat_stream(req):
            if ev.type == "delta_text" and ev.text:
                _append_log(state, "text", ev.text)
                text_parts.append(ev.text)

            elif ev.type == "delta_thinking" and ev.text:
                _append_log(state, "thinking", ev.text)

            elif ev.type == "tool_call" and ev.tool_call:
                tool_calls.append(ev.tool_call)

            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")

            elif ev.type == "done":
                break

        # If no tool calls, we are done.
        if not tool_calls:
            return "".join(text_parts)

        # Execute tool calls deterministically, append results, then loop.
        for tc in tool_calls:
            handler = tools.handlers.get(tc.name)
            if handler is None:
                raise RuntimeError(f"Tool call requested unknown tool: {tc.name}")

            _emit_node_event(
                state,
                phase="progress",
                msg=f"Tool call: {tc.name}",
                data={"tool_call_id": tc.id, "tool": tc.name},
            )

            result_text = handler(tc.arguments_json)

            # Append tool result. Canonical link uses tool_call_id.
            messages.append(
                Message(
                    role="tool",
                    content=result_text,
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

    raise RuntimeError(f"Tool loop exceeded max_steps={max_steps} for node {NODE_ID}")


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # Tools for this node: keep disabled by default in the template.
    # When you want to exercise tools, fill these in for your node.
    tool_spec: Optional[ToolSpec] = None
    # Example (uncomment and customize):
    #
    # tool_spec = ToolSpec(
    #     defs=[
    #         ToolDef(
    #             name="echo",
    #             description="Echo back the provided text.",
    #             parameters={
    #                 "type": "object",
    #                 "properties": {"text": {"type": "string"}},
    #                 "required": ["text"],
    #             },
    #         ),
    #     ],
    #     handlers={
    #         "echo": lambda args_json: json.dumps({"echo": json.loads(args_json)["text"]}),
    #     },
    # )

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        _emit_node_event(state, phase="start", msg=f"Running {NODE_ID}")

        try:
            # ---- Inputs (keep small & explicit) ----
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            # You can add more fields as needed:
            # status = str(state.get("runtime", {}).get("status", "") or "")

            # ---- Render prompt (deterministic token replacement) ----
            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": ROLE_KEY,
                },
            )

            # ---- Canonical messages ----
            #
            # For now we preserve the “prompt-as-user-message” style.
            # When you’re ready, split prompt into system + user messages.
            messages: List[Message] = [
                Message(role="user", content=prompt),
            ]

            # ---- Resolve model/params/format from deps+config ----
            #
            # Convention: use deps.models[ROLE_KEY] when it exists,
            # otherwise fall back to deps.models["final"] (but you can choose strictness per node).
            model = deps.models.get(ROLE_KEY) or deps.models.get("final")
            if not model:
                raise RuntimeError(f"No model configured for role '{ROLE_KEY}'")

            # Role params + format:
            # In your current v2, deps.llm_final/llm_router expose params, but not arbitrary role objects.
            # Template assumes you’ll either:
            #   A) add deps.llm_roles[role] later, or
            #   B) inline per-node params from config into deps for this role.
            #
            # For now, use llm_final params as a safe placeholder for non-router nodes.
            # When you instantiate a node from this template, update this line to the correct role params.
            params = deps.llm_final.params

            # response_format:
            # For structured nodes, set to "json" (or schema dict).
            # For freeform nodes, keep None.
            response_format = None  # set to "json" for structured nodes

            # stop/limits/tool loop:
            max_steps = 16  # match your global tool step limit later

            # ---- Call LLM (streaming) ----
            text = _run_tool_loop(
                deps=deps,
                state=state,
                model=model,
                params=params,
                response_format=response_format,
                messages=messages,
                tools=tool_spec,
                max_steps=max_steps,
            )

            # ---- Store output (one narrow location) ----
            #
            # Choose one state key per node and keep it stable.
            state.setdefault("runtime", {})[f"{NODE_ID}.text"] = text

            _emit_node_event(state, phase="end", msg=f"Done {NODE_ID}")
            return state

        except Exception as e:
            _emit_node_event(state, phase="error", msg=f"Failed {NODE_ID}", data={"error": str(e)})
            raise

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
