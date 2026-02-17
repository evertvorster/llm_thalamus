from __future__ import annotations

from typing import Callable

from runtime.deps import Deps, _chat_params_from_mapping
from runtime.prompting import render_tokens
from runtime.providers.types import ChatRequest, Message
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

        # Preserve current behavior: render the full prompt template into a single user message.
        prompt = render_tokens(
            template,
            {
                "USER_MESSAGE": user_text,
                "STATUS": status,
                "WORLD_JSON": world_json,
            },
        )

        req = ChatRequest(
            model=deps.models["final"],
            messages=[Message(role="user", content=prompt)],
            response_format=None,  # answer is not a structured JSON node
            params=_chat_params_from_mapping(deps.llm_final.params),
            stream=True,
        )

        buf = state.setdefault("_runtime_logs", [])
        out: list[str] = []

        for ev in deps.provider.chat_stream(req):
            if ev.type == "delta_text" and ev.text:
                buf.append(ev.text)
                out.append(ev.text)
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
