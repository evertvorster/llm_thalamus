from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.answer"
GROUP = "llm"
LABEL = "Answer"
PROMPT_NAME = "runtime_answer"  # resources/prompts/runtime_answer.txt


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            status = str(state.get("runtime", {}).get("status", "") or "")

            world_json = json.dumps(state.get("world", {}) or {}, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "STATUS": status,
                    "WORLD_JSON": world_json,
                },
            )

            # The UI expects one assistant message per turn, but we want it to arrive
            # as soon as this node is done (not after reflect). We emit assistant_* here.
            turn_id = str(state.get("runtime", {}).get("turn_id", "") or "")
            message_id = f"assistant:{turn_id}" if turn_id else "assistant"

            emitter.emit(emitter.factory.assistant_start(message_id=message_id))

            out_parts: list[str] = []

            for ev in chat_stream(
                provider=deps.provider,
                model=deps.models["final"],
                messages=[Message(role="user", content=prompt)],
                params=deps.llm_final.params,
                response_format=None,
                tools=None,
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    # Treat model output as streamable content; show it in thinking log too.
                    span.thinking(ev.text)
                    out_parts.append(ev.text)
                    emitter.emit(emitter.factory.assistant_delta(message_id=message_id, text=ev.text))

                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            emitter.emit(emitter.factory.assistant_end(message_id=message_id))

            answer = "".join(out_parts)
            state.setdefault("final", {})["answer"] = answer

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
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
