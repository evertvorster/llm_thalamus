from __future__ import annotations

from typing import Callable

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream


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

        raw_parts: list[str] = []

        for ev in chat_stream(
            provider=deps.provider,
            model=deps.models["router"],
            messages=[Message(role="user", content=prompt)],
            params=deps.llm_router.params,
            response_format=deps.llm_router.response_format,
            tools=None,  # router is structured; tools are disabled here
            max_steps=deps.tool_step_limit,
        ):
            if ev.type == "delta_text" and ev.text:
                state.setdefault("_runtime_logs", []).append(ev.text)
                raw_parts.append(ev.text)

            elif ev.type == "delta_thinking" and ev.text:
                state.setdefault("_runtime_logs", []).append(ev.text)

            elif ev.type == "tool_call" or ev.type == "tool_result":
                # Tools are disabled for router, but tool_loop may still yield these in future.
                # Ignore safely.
                pass

            elif ev.type == "usage":
                # Ignore for now (could be recorded later).
                pass

            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")

            elif ev.type == "done":
                break

        raw_text = "".join(raw_parts)

        import json

        obj = json.loads(raw_text)

        route = str(obj.get("route", "answer") or "answer").strip() or "answer"
        language = str(obj.get("language", "en") or "en").strip() or "en"
        status = str(obj.get("status", "") or "").strip()

        state.setdefault("task", {})["language"] = language
        state.setdefault("runtime", {})["status"] = status

        # Minimal graph: router -> answer; route not used yet.
        _ = route
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
