from __future__ import annotations

import json
from typing import Callable, List

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.reflect_topics"
GROUP = "llm"
LABEL = "Reflect Topics"
PROMPT_NAME = "runtime_reflect_topics"


def _append_log(state: State, text: str) -> None:
    state.setdefault("_runtime_logs", []).append(text)


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

        world = state.setdefault("world", {})
        prev_topics = world.get("topics", [])
        if not isinstance(prev_topics, list):
            prev_topics = []
        prev_topics_json = json.dumps(prev_topics, ensure_ascii=False)

        user_text = str(state.get("task", {}).get("user_text", "") or "")
        assistant_text = str(state.get("final", {}).get("answer", "") or "")

        prompt = render_tokens(
            template,
            {
                "PREV_TOPICS_JSON": prev_topics_json,
                "USER_MESSAGE": user_text,
                "ASSISTANT_MESSAGE": assistant_text,
            },
        )

        # For now, reflect_topics uses the "final" role model/params (strict, no config expansion yet)
        model = deps.models["final"]
        params = deps.llm_final.params

        # Force JSON output for this node (topics are a structured contract)
        response_format = "json"

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
                # keep logs visible for debugging: the router/answer already do this
                _append_log(state, ev.text)
                raw_parts.append(ev.text)

            elif ev.type == "delta_thinking" and ev.text:
                _append_log(state, ev.text)

            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")

            elif ev.type == "done":
                break

        raw_text = "".join(raw_parts).strip()
        obj = json.loads(raw_text)  # strict; if it fails, that's a prompt/model issue

        topics = _coerce_topics(obj.get("topics"))
        # Guardrails: keep it small and useful
        if len(topics) > 5:
            topics = topics[:5]

        world["topics"] = topics
        return state

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
