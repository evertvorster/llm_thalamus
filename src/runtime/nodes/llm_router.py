from __future__ import annotations

from typing import Callable

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.registry import NodeSpec, register
from runtime.state import State


NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_NAME = "runtime_router"  # resources/prompts/runtime_router.txt


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        user_text = str(state.get("task", {}).get("user_text", "") or "")
        now = str(state.get("world", {}).get("now", "") or "")
        tz = str(state.get("world", {}).get("tz", "") or "")

        prompt = render_tokens(
            template,
            {
                "USER_MESSAGE": user_text,
                "NOW": now,
                "TZ": tz,
            },
        )

        # Stream from LLM; buffer logs for runner to flush.
        buf = state.setdefault("_runtime_logs", [])
        raw = []
        for _, txt in deps.llm_router.generate_stream(prompt):
            buf.append(txt)
            raw.append(txt)
        raw_text = "".join(raw)

        # Router contract: must output JSON object. We keep bootstrap strict:
        # if it doesn't, we route to answer anyway.
        route = "answer"
        language = "en"
        status = ""

        # Tiny tolerant parse: find first '{'...' }' and json.loads it if possible.
        try:
            import json

            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start >= 0 and end > start:
                obj = json.loads(raw_text[start : end + 1])
                route = str(obj.get("route", "answer") or "answer").strip() or "answer"
                language = str(obj.get("language", "en") or "en").strip() or "en"
                status = str(obj.get("status", "") or "").strip()
        except Exception:
            pass

        state.setdefault("task", {})["language"] = language
        state.setdefault("runtime", {})["status"] = status

        # Bootstrap graph is fixed router->answer, so we don't need to store next node yet.
        # (Later, conditional routing will use a state key here.)
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
