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


NODE_ID = "llm.memory_writer"
GROUP = "llm"
LABEL = "Memory Writer"
PROMPT_NAME = "runtime_memory_writer"
ROLE_KEY = "reflect"


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _parse_first_json_object(raw: str) -> dict[str, Any]:
    if not raw:
        raise RuntimeError("empty model output (expected JSON object)")
    s = raw.strip()

    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
            s = "\n".join(lines[1:-1]).strip()

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


def _normalize_memory_text(topic: str, text: str) -> str:
    topic = (topic or "").strip()
    text = (text or "").strip()

    if not topic:
        return text

    prefix = f"[{topic}] "
    if text.startswith(prefix):
        return text
    # If user already included bracketed topic (maybe different spacing), don't duplicate aggressively
    if text.startswith("[") and "]" in text[:64]:
        return text
    return prefix + text


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # Policy-gated tools for this node
    toolset = services.tools.toolset_for_node("memory_writer")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            answer_text = str(state.get("final", {}).get("answer", "") or "")

            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            topics = _ensure_list(world.get("topics"))
            topics_json = json.dumps(topics, ensure_ascii=False)

            now_iso = str(state.get("runtime", {}).get("now_iso", "") or "")
            timezone = str(state.get("runtime", {}).get("timezone", "") or "")

            prompt = render_tokens(
                template,
                {
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": ROLE_KEY,
                    "USER_MESSAGE": user_text,
                    "ASSISTANT_ANSWER": answer_text,
                    "WORLD_JSON": world_json,
                    "TOPICS_JSON": topics_json,
                    "NOW_ISO": now_iso,
                    "TIMEZONE": timezone,
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

            # We expect a summary JSON from the model after tool calls.
            stored = obj.get("stored", [])
            stored_n = obj.get("stored_count", None)

            # Append a status line (context-scoped issues)
            ctx = state.setdefault("context", {})
            if not isinstance(ctx, dict):
                ctx = {}
                state["context"] = ctx
            issues = ctx.get("issues")
            if not isinstance(issues, list):
                issues = []
                ctx["issues"] = issues

            if isinstance(stored_n, int):
                issues.append(f"memory_writer: stored_count={stored_n}")
            else:
                # fall back to length of stored list if present
                if isinstance(stored, list):
                    issues.append(f"memory_writer: stored_count={len(stored)}")
                else:
                    issues.append("memory_writer: completed (stored_count unknown)")

            # Optionally also record a source entry summarizing storage (not the memories themselves)
            # This is diagnostics only; real memories live in OpenMemory.
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
                    "kind": "notes",
                    "title": "Memory writer status",
                    "items": [
                        {"stored_count": stored_n if isinstance(stored_n, int) else None}
                    ],
                }
            )

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