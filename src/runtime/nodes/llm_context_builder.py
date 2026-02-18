from __future__ import annotations

import json
from typing import Callable, List

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
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


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # LangGraph node key is "context_builder" (see graph_build.py)
    toolset = services.tools.toolset_for_node("context_builder")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                },
            )

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format

            messages: List[Message] = [Message(role="user", content=prompt)]

            text_parts: list[str] = []
            for ev in chat_stream(
                provider=deps.provider,
                model=model,
                messages=messages,
                params=role_params,
                response_format=response_format,
                tools=toolset,
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

            out_text = "".join(text_parts).strip()
            try:
                ctx_obj = json.loads(out_text)
            except Exception as e:
                raise RuntimeError(f"context_builder: output not valid JSON: {e}") from e

            if not isinstance(ctx_obj, dict):
                raise RuntimeError("context_builder: output must be a JSON object")

            # Store on state for downstream nodes.
            state["context"] = ctx_obj

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
