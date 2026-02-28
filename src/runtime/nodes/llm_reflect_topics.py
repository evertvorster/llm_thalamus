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
        user_text = str(state.get("task", {}).get("user_text", "") or "")

        # Most recent assistant output (Answer node stores it here)
        assistant_msg = str(state.get("final", {}).get("answer", "") or "")

        # Previous topics (before update)
        prev_topics = (state.get("world", {}) or {}).get("topics", []) or []
        if not isinstance(prev_topics, list):
            prev_topics = []
        prev_topics_json = json.dumps(prev_topics, ensure_ascii=False)

        world_json = stable_json(state.get("world", {}) or {})

        tokens = {
            "NODE_ID": NODE_ID,
            "ROLE_KEY": ROLE_KEY,
            "USER_MESSAGE": user_text,
            "WORLD_JSON": world_json,
            # Required by runtime_reflect_topics prompt:
            "ASSISTANT_MESSAGE": assistant_msg,
            "PREV_TOPICS_JSON": prev_topics_json,
        }

        return run_structured_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            tokens=tokens,
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
