from __future__ import annotations

import json
from typing import Callable, Dict, List, Any

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"  # must exist in cfg.llm.roles


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _clamp_int(v: Any, lo: int, hi: int) -> int:
    try:
        iv = int(v)
    except Exception:
        return lo
    if iv < lo:
        return lo
    if iv > hi:
        return hi
    return iv


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            # Hard cap: use the same knob that trims chat history on disk
            # (you restored thalamus.message_history; it is exposed as cfg.message_history_max / similar)
            # We access it through deps (which already has cfg values).
            max_turns = int(getattr(deps, "message_history_max", 30))

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                    "MAX_CHAT_TURNS": str(max_turns),
                },
            )

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format

            messages: List[Message] = [Message(role="user", content=prompt)]

            text_parts: List[str] = []
            for ev in chat_stream(
                provider=deps.provider,
                model=model,
                messages=messages,
                params=role_params,
                response_format=response_format,
                tools=None,
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    text_parts.append(ev.text)
                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)
                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")
                elif ev.type == "done":
                    break

            plan_text = "".join(text_parts).strip()
            try:
                plan = json.loads(plan_text)
            except Exception as e:
                raise RuntimeError(f"context_builder: planner output not valid JSON: {e}") from e

            if not isinstance(plan, dict):
                raise RuntimeError("context_builder: planner output must be a JSON object")

            requested = _clamp_int(plan.get("requested_chat_turns", 0), 0, max_turns)
            reason = plan.get("reason", "")
            if not isinstance(reason, str):
                reason = str(reason)

            # Read chat tail mechanically (no tool-calling yet).
            # We deliberately keep this small and deterministic.
            from controller.chat_history import read_tail  # local import to avoid UI import cycles

            turns = read_tail(deps.message_file, limit=requested)

            # Structure context for downstream nodes
            ctx = state.setdefault("context", {})
            ctx["chat"] = {
                "requested_n": requested,
                "used_n": len(turns),
                "reason": reason.strip(),
                "turns": turns,
            }
            ctx["memories"] = {"items": [], "k": 0, "notes": ""}
            ctx["episodes"] = {"rows": [], "k": 0, "notes": ""}

            # Optional issues channel for answer node
            issues = plan.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            state.setdefault("runtime", {})["issues"] = issues

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
