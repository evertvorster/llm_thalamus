from __future__ import annotations

from typing import Callable

from orchestrator.deps import Deps
from orchestrator.state import State

from runtime.graph_nodes import collect_streamed_response
from runtime.prompting import render_tokens
from runtime.registry import NodeSpec, register


NODE_ID = "llm.answer"
GROUP = "llm"
LABEL = "Answer"
PROMPT_NAME = "runtime_answer"  # resources/prompts/runtime_answer.txt


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.prompt_loader.load(PROMPT_NAME)  # :contentReference[oaicite:8]{index=8}
    model = deps.models.get("final")  # config extraction guarantees models["final"] exists in old system. :contentReference[oaicite:9]{index=9}

    def node(state: State) -> State:
        state["runtime"]["node_trace"].append(NODE_ID)

        prompt = render_tokens(
            template,
            {
                "USER_MESSAGE": state["task"]["user_input"],
                "STATUS": str(state["runtime"].get("status", "") or ""),
                "WORLD_JSON": str(state.get("world", {})),
            },
        )

        stream = deps.llm_generate_stream(model, prompt)

        def _on_chunk(t: str) -> None:
            state.setdefault("_runtime_logs", []).append(t)

        answer = collect_streamed_response(stream, on_chunk=_on_chunk)

        state["final"]["answer"] = answer
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
