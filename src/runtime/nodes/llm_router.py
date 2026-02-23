from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream
from runtime.services import RuntimeServices


NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_NAME = "runtime_router"  # resources/prompts/runtime_router.txt


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def make(deps: Deps, services: RuntimeServices | None = None) -> Callable[[State], State]:
    _ = services
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)

        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            now = str(state.get("runtime", {}).get("now_iso", "") or "")
            tz = str(state.get("runtime", {}).get("timezone", "") or "")

            world_json = json.dumps(
                state.get("world", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "NOW": now,
                    "TZ": tz,
                    "WORLD_JSON": world_json,
                },
            )

            raw_parts: list[str] = []

            for ev in chat_stream(
                provider=deps.provider,
                model=deps.get_llm("router").model,
                messages=[Message(role="user", content=prompt)],
                params=deps.get_llm("router").params,
                response_format=deps.get_llm("router").response_format,
                tools=None,  # router is structured; tools are disabled here
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    # Router output is structured JSON; do NOT treat as "thinking".
                    raw_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    # Only actual model thinking goes to the thinking log.
                    span.thinking(ev.text)

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            raw_text = "".join(raw_parts).strip()
            obj = json.loads(raw_text)
            if not isinstance(obj, dict):
                raise RuntimeError("router: output must be a JSON object")

            route = str(obj.get("route", "answer") or "answer").strip() or "answer"
            language = str(obj.get("language", "en") or "en").strip() or "en"
            status = str(obj.get("status", "") or "").strip()

            state.setdefault("task", {})["language"] = language
            state.setdefault("task", {})["route"] = route  # <-- critical for branching
            state.setdefault("runtime", {})["status"] = status

            span.end_ok()
            return state

        except Exception as e:
            span.end_error(code="NODE_ERROR", message=str(e))
            raise

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role="router",
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
