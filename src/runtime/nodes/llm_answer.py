from __future__ import annotations

from typing import Callable

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.registry import NodeSpec, register
from runtime.state import State


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
        world_json = str(state.get("world", {}) or {})

        prompt = render_tokens(
            template,
            {
                "USER_MESSAGE": user_text,
                "STATUS": status,
                "WORLD_JSON": world_json,
            },
        )

        buf = state.setdefault("_runtime_logs", [])
        out = []
        for _, txt in deps.llm_final.generate_stream(prompt):
            buf.append(txt)
            out.append(txt)

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
