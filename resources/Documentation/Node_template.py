# src/runtime/nodes/<group>_<name>.py
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Optional

from runtime.deps import Deps
from runtime.prompting import render_tokens
from runtime.providers.types import Message, StreamEvent, ToolDef
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream, ToolSet


# ---- Node metadata ----

NODE_ID = "<group>.<name>"
GROUP = "<group>"
LABEL = "<Human label>"
PROMPT_NAME = "<prompt_name>"
ROLE_KEY = "<role_key>"


# ---- Logging helpers ----

def _append_log(state: State, text: str) -> None:
    state.setdefault("_runtime_logs", []).append(text)


def _emit_node_event(state: State, *, phase: str, msg: str) -> None:
    state.setdefault("_runtime_events", []).append(
        {
            "type": "node_event",
            "node_id": NODE_ID,
            "group": GROUP,
            "phase": phase,
            "msg": msg,
        }
    )


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # ---- Optional tools (disabled by default) ----
    tool_set: Optional[ToolSet] = None

    # Example tool configuration:
    #
    # tool_set = ToolSet(
    #     defs=[
    #         ToolDef(
    #             name="echo",
    #             description="Echo back provided text.",
    #             parameters={
    #                 "type": "object",
    #                 "properties": {"text": {"type": "string"}},
    #                 "required": ["text"],
    #             },
    #         ),
    #     ],
    #     handlers={
    #         "echo": lambda args_json: json.dumps(
    #             {"echo": json.loads(args_json)["text"]}
    #         ),
    #     },
    # )

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        _emit_node_event(state, phase="start", msg=f"Running {NODE_ID}")

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                    "NODE_ID": NODE_ID,
                    "ROLE_KEY": ROLE_KEY,
                },
            )

            messages: List[Message] = [
                Message(role="user", content=prompt),
            ]

            # Resolve model strictly from config
            model = deps.models.get(ROLE_KEY)
            if not model:
                raise RuntimeError(f"No model configured for role '{ROLE_KEY}'")

            params = getattr(deps, f"llm_{ROLE_KEY}", None)
            if params is None:
                # fallback to final role params if role-specific not implemented yet
                params = deps.llm_final

            role_params = params.params
            response_format = params.response_format

            text_parts: List[str] = []

            for ev in chat_stream(
                provider=deps.provider,
                model=model,
                messages=messages,
                params=role_params,
                response_format=response_format,
                tools=tool_set,
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    _append_log(state, ev.text)
                    text_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    _append_log(state, ev.text)

                elif ev.type == "tool_call":
                    _append_log(state, f"[tool_call] {ev.tool_call.name}")

                elif ev.type == "tool_result" and ev.text:
                    _append_log(state, f"[tool_result] {ev.text}")

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            text = "".join(text_parts)

            state.setdefault("runtime", {})[f"{NODE_ID}.text"] = text

            _emit_node_event(state, phase="end", msg=f"Done {NODE_ID}")
            return state

        except Exception as e:
            _emit_node_event(state, phase="error", msg=str(e))
            raise

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
