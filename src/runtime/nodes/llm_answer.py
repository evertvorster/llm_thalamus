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
        user_text = str(state.get("task", {}).get("user_text", "") or "")
        status = str(state.get("runtime", {}).get("status", "") or "")

        now_iso = str(state.get("runtime", {}).get("now_iso", "") or "")
        timezone = str(state.get("runtime", {}).get("timezone", "") or "")

        world_json = stable_json(state.get("world", {}) or {})
        context_json = stable_json(state.get("context", {}) or {})
        issues_json = stable_json(state.get("runtime", {}).get("issues", []) or [])

        tokens = {
            "USER_MESSAGE": user_text,
            "STATUS": status,
            "WORLD_JSON": world_json,
            "CONTEXT_JSON": context_json,
            "ISSUES_JSON": issues_json,
            "NOW_ISO": now_iso,
            "TIMEZONE": timezone,
        }

        turn_id = str(state.get("runtime", {}).get("turn_id", "") or "")
        message_id = f"assistant:{turn_id}" if turn_id else "assistant"

        answer = run_streaming_answer_node(
            state=state,
            deps=deps,
            node_id=NODE_ID,
            label=LABEL,
            role_key="answer",
            prompt_name=PROMPT_NAME,
            tokens=tokens,
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
