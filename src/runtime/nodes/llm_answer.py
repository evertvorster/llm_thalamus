from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.answer"
GROUP = "llm"
LABEL = "Answer"
PROMPT_NAME = "runtime_answer"  # resources/prompts/runtime_answer.txt


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

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

        out: list[str] = []

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
                state.setdefault("_runtime_logs", []).append(ev.text)
                out.append(ev.text)
            elif ev.type == "delta_thinking" and ev.text:
                state.setdefault("_runtime_logs", []).append(ev.text)
            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")
            elif ev.type == "done":
                break

        answer = "".join(out)
        state.setdefault("final", {})["answer"] = answer
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
