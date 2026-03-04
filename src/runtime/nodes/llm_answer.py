from __future__ import annotations
import json
from typing import Callable
from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.services import RuntimeServices
from runtime.nodes_common import stable_json, run_streaming_answer_node

NODE_ID = "llm.answer"
GROUP = "llm"
LABEL = "Answer"
PROMPT_NAME = "runtime_answer"  # resources/prompts/runtime_answer.txt

def make(deps: Deps, services: RuntimeServices | None = None) -> Callable[[State], State]:
    _ = services

    def node(state: State) -> State:
        turn_id = str(state.get("runtime", {}).get("turn_id", "") or "")
        message_id = f"assistant:{turn_id}" if turn_id else "assistant"

        # TokenBuilder handles prompt rendering automatically via GLOBAL_TOKEN_SPEC
        answer = run_streaming_answer_node(
            state=state,
            deps=deps,
            node_id=NODE_ID,
            label=LABEL,
            role_key="answer",
            prompt_name=PROMPT_NAME,
            message_id=message_id,
        )

        state.setdefault("final", {})["answer"] = answer
        return state

    return node

register(NodeSpec(
    node_id=NODE_ID,
    group=GROUP,
    label=LABEL,
    role="answer",
    make=make,
    prompt_name=PROMPT_NAME,
))