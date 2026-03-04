from __future__ import annotations
import json
from typing import Callable
from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import stable_json, run_structured_node

NODE_ID = "llm.reflect_topics"
GROUP = "llm"
LABEL = "Reflect Topics"
PROMPT_NAME = "runtime_reflect_topics"
ROLE_KEY = "reflect"

def make(deps: Deps, services: RuntimeServices | None = None) -> Callable[[State], State]:
    _ = services

    def apply_result(state: State, obj: dict) -> None:
        topics = obj.get("topics")
        if isinstance(topics, list):
            state.setdefault("world", {})["topics"] = topics

    def node(state: State) -> State:
        # TokenBuilder handles prompt rendering automatically via GLOBAL_TOKEN_SPEC
        return run_structured_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            node_key_for_tools=None,
            apply_result=apply_result,
        )

    return node

register(NodeSpec(
    node_id=NODE_ID,
    group=GROUP,
    label=LABEL,
    role=ROLE_KEY,
    make=make,
    prompt_name=PROMPT_NAME,
))