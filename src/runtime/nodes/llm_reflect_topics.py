from __future__ import annotations

import json
from typing import Callable, List

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.reflect_topics"
GROUP = "llm"
LABEL = "Reflect Topics"
PROMPT_NAME = "runtime_reflect_topics"


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _coerce_topics(value) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for x in value:
        if isinstance(x, str):
            s = x.strip()
            if s:
                out.append(s)
    # de-dupe while preserving order
    seen = set()
    deduped: List[str] = []
    for t in out:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        deduped.append(t)
    return deduped


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            world = state.setdefault("world", {})
            prev_topics = world.get("topics", [])
            if not isinstance(prev_topics, list):
                prev_topics = []
            prev_topics_json = json.dumps(prev_topics, ensure_ascii=False)

            user_text = str(state.get("task", {}).get("user_text", "") or "")
            assistant_text = str(state.get("final", {}).get("answer", "") or "")

            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    # Template tokens
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": "reflect",
                    "WORLD_JSON": world_json,
                    # Reflect-specific tokens
                    "PREV_TOPICS_JSON": prev_topics_json,
                    "USER_MESSAGE": user_text,
                    "ASSISTANT_MESSAGE": assistant_text,
                },
            )

            model = deps.models["reflect"]
            params = deps.llm_reflect.params
            response_format = deps.llm_reflect.response_format

            raw_parts: list[str] = []
            for ev in chat_stream(
                provider=deps.provider,
                model=model,
                messages=[Message(role="user", content=prompt)],
                params=params,
                response_format=response_format,
                tools=None,
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    # Reflect output is structured JSON; do NOT treat as "thinking".
                    raw_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            raw_text = "".join(raw_parts).strip()
            obj = json.loads(raw_text)  # strict; if it fails, prompt/model issue

            topics = _coerce_topics(obj.get("topics"))
            if len(topics) > 5:
                topics = topics[:5]

            world["topics"] = topics

            # Make it visible in thalamus log without polluting thinking.
            span.log(
                level="info",
                logger="runtime.nodes.reflect_topics",
                message="topics updated",
                fields={"topics": topics},
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
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
