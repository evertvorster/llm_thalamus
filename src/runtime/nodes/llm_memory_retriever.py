from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.memory_retriever"
GROUP = "llm"
LABEL = "Memory Retriever"
PROMPT_NAME = "runtime_memory_retriever"
ROLE_KEY = "reflect"


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _parse_first_json_object(raw: str) -> dict[str, Any]:
    """
    Robust parser: extract the first JSON object from a text response.
    This matches the Node_template guidance.
    """
    if not raw:
        raise RuntimeError("empty model output (expected JSON object)")

    s = raw.strip()

    # Common fences
    if s.startswith("```"):
        # strip outer code-fence if present
        lines = s.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
            s = "\n".join(lines[1:-1]).strip()

    # Find first '{' and parse by brace depth
    start = s.find("{")
    if start < 0:
        raise RuntimeError(f"no JSON object found in output: {raw!r}")

    depth = 0
    end = -1
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        raise RuntimeError(f"unterminated JSON object in output: {raw!r}")

    obj_text = s[start:end]
    try:
        obj = json.loads(obj_text)
    except Exception as e:
        raise RuntimeError(f"output JSON parse failed: {e}: {obj_text!r}") from e

    if not isinstance(obj, dict):
        raise RuntimeError("output must be a JSON object")
    return obj


def _ensure_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _ensure_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # Policy-gated tools for this node
    toolset = services.tools.toolset_for_node("memory_retriever")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")

            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            ctx = state.get("context", {}) or {}
            if not isinstance(ctx, dict):
                ctx = {}
            context_json = json.dumps(ctx, ensure_ascii=False, sort_keys=True)

            topics = _ensure_list(world.get("topics"))
            topics_json = json.dumps(topics, ensure_ascii=False)

            now_iso = str(state.get("runtime", {}).get("now_iso", "") or "")
            timezone = str(state.get("runtime", {}).get("timezone", "") or "")

            # context_builder may pass an explicit desired memory count in context.request
            desired_n = None
            req = _ensure_dict(ctx.get("request"))
            if isinstance(req.get("memories_n"), int):
                desired_n = int(req["memories_n"])
            if desired_n is None:
                desired_n = 5  # safe default (context_builder can override)

            prompt = render_tokens(
                template,
                {
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": ROLE_KEY,
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                    "CONTEXT_JSON": context_json,
                    "TOPICS_JSON": topics_json,
                    "NOW_ISO": now_iso,
                    "TIMEZONE": timezone,
                    "REQUESTED_LIMIT": str(desired_n),
                },
            )

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            params = llm.params
            response_format = llm.response_format  # json

            raw_parts: list[str] = []
            for ev in chat_stream(
                provider=deps.provider,
                model=model,
                messages=[Message(role="user", content=prompt)],
                params=params,
                response_format=response_format,
                tools=toolset,
                max_steps=deps.tool_step_limit,
                emitter=emitter,
                node_id=span.node_id,
                span_id=span.span_id,
            ):
                if ev.type == "delta_text" and ev.text:
                    raw_parts.append(ev.text)
                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)
                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")
                elif ev.type == "done":
                    break

            out_text = "".join(raw_parts).strip()
            obj = _parse_first_json_object(out_text)

            did_query = bool(obj.get("did_query", False))
            query_text = str(obj.get("query_text", "") or "")
            returned = obj.get("returned", None)
            items = obj.get("items", [])

            if did_query:
                if not isinstance(items, list):
                    raise RuntimeError("memory_retriever: items must be a list when did_query=true")

                # Append typed source into context.sources (Option A)
                ctx = state.setdefault("context", {})
                if not isinstance(ctx, dict):
                    ctx = {}
                    state["context"] = ctx

                ctx_inner = ctx.get("context")
                if not isinstance(ctx_inner, dict):
                    ctx_inner = {}
                    ctx["context"] = ctx_inner

                sources = ctx_inner.get("sources")
                if not isinstance(sources, list):
                    sources = []
                    ctx_inner["sources"] = sources

                sources.append(
                    {
                        "kind": "memories",
                        "title": "Relevant long-term memories",
                        "items": items,
                        "meta": {
                            "query_text": query_text,
                            "requested_limit": desired_n,
                            "returned": returned if isinstance(returned, int) else len(items),
                        },
                    }
                )

                # Append status line for visibility
                issues = ctx.get("issues")
                if not isinstance(issues, list):
                    issues = []
                    ctx["issues"] = issues
                issues.append(
                    f"memory_retriever: did_query=true query={query_text!r} returned={len(items)}"
                )
            else:
                # If no query, still append a status line
                ctx = state.setdefault("context", {})
                if not isinstance(ctx, dict):
                    ctx = {}
                    state["context"] = ctx
                issues = ctx.get("issues")
                if not isinstance(issues, list):
                    issues = []
                    ctx["issues"] = issues
                issues.append("memory_retriever: did_query=false (topics not relevant)")

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