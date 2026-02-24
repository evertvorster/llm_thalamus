from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import ToolSet, chat_stream


# ---- Node metadata ----
NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"     # resources/prompts/runtime_context_builder.txt
ROLE_KEY = "planner"                        # must exist in cfg.llm.roles


# ---- Emitter contract ----

def _get_emitter(state: State) -> TurnEmitter:
    em = (state.get("runtime") or {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _parse_first_json_object(text: str) -> dict:
    """Parse the first JSON object found in `text`, tolerating trailing junk."""
    s = (text or "").strip()

    # Strip common markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)

    # Start at first object brace.
    i = s.find("{")
    if i > 0:
        s = s[i:]

    obj, _idx = json.JSONDecoder().raw_decode(s)
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


def _stable_json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _ctx_dict(state: State) -> Dict[str, Any]:
    ctx = state.get("context")
    if isinstance(ctx, dict):
        return ctx
    ctx = {}
    state["context"] = ctx
    return ctx


def _ctx_payload(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Return the nested payload dict under ctx['context'] (create if missing)."""
    payload = ctx.get("context")
    if isinstance(payload, dict):
        return payload
    payload = {}
    ctx["context"] = payload
    return payload


def _merge_context(state: State, produced: Dict[str, Any]) -> None:
    """Merge model-produced JSON into state['context'] with 'slot replacement' semantics.

    Slots (authoritative replacements):
      - state['context']['context']['chat_history']
      - state['context']['context']['memories']
      - state['context']['context']['memory_request'] (optional planning directive)
    Controller directive:
      - state['context']['next'] (aliases accepted in graph selector; we write 'next')
    """
    ctx = _ctx_dict(state)
    payload = _ctx_payload(ctx)

    # Top-level simple fields.
    if isinstance(produced.get("complete"), bool):
        ctx["complete"] = bool(produced["complete"])

    # Issues channel (optional).
    issues = produced.get("issues")
    if isinstance(issues, list):
        # Only keep strings; avoid surprises.
        ctx["issues"] = [str(x) for x in issues if isinstance(x, (str, int, float, bool))]

    # Routing directive (default to answer when absent).
    nxt = produced.get("next")
    if not isinstance(nxt, str) or not nxt.strip():
        nxt = "answer"
    nxt = nxt.strip()

    # Future-proof: allow planner, but graph currently supports memory_retriever|answer.
    if nxt not in ("memory_retriever", "answer", "planner"):
        nxt = "answer"
    ctx["next"] = nxt

    # Nested context payload replacement semantics.
    produced_payload = produced.get("context")
    if isinstance(produced_payload, dict):
        if "chat_history" in produced_payload:
            payload["chat_history"] = produced_payload.get("chat_history")
        if "memories" in produced_payload:
            payload["memories"] = produced_payload.get("memories")
        if "memory_request" in produced_payload:
            payload["memory_request"] = produced_payload.get("memory_request")

        # Optional small scratch notes (kept short by prompt).
        if "notes" in produced_payload:
            payload["notes"] = produced_payload.get("notes")


def make(deps: Deps, services) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        # Trace
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        # Hop counter for safety (graph has a guard; we increment here for observability).
        rt = state.setdefault("runtime", {})
        try:
            rt["context_hops"] = int(rt.get("context_hops") or 0) + 1
        except Exception:
            rt["context_hops"] = 1

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str((state.get("task") or {}).get("user_text", "") or "")
            world = state.get("world") or {}
            ctx = _ctx_dict(state)

            prompt = render_tokens(
                template,
                {
                    # Project-wide convention: prompts use <<TOKENS>> markers.
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": _stable_json(world),
                    "EXISTING_CONTEXT_JSON": _stable_json(ctx),
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": ROLE_KEY,
                },
            )

            messages: List[Message] = [Message(role="user", content=prompt)]

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format  # should be JSON for this node

            # Tools for this node are assembled by the capability firewall.
            tool_set: Optional[ToolSet] = None
            if services is not None and getattr(services, "tools", None) is not None:
                tool_set = services.tools.toolset_for_node("context_builder")

            text_parts: List[str] = []

            for ev in chat_stream(
                provider=deps.provider,
                emitter=emitter,
                node_id=NODE_ID,
                span_id=span.span_id if hasattr(span, "span_id") else None,
                model=model,
                messages=messages,
                params=role_params,
                response_format=response_format,
                tools=tool_set,
                max_steps=getattr(deps, "tool_step_limit", 6),
            ):
                if ev.type == "delta_text" and ev.text:
                    text_parts.append(ev.text)
                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)
                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")
                elif ev.type == "done":
                    break

            text = "".join(text_parts)
            obj = _parse_first_json_object(text)

            _merge_context(state, obj)

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
        prompt_name=PROMPT_NAME,
    )
)
