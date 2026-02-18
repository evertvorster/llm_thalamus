from __future__ import annotations

import json
from typing import Callable, List, Optional

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message, ToolDef
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream, ToolSet


# ---- Node metadata ----

NODE_ID = "<group>.<name>"
GROUP = "<group>"
LABEL = "<Human label>"
PROMPT_NAME = "<prompt_name>"     # resources/prompts/<prompt_name>.txt
ROLE_KEY = "<role_key>"           # must exist in cfg.llm.roles and therefore deps.get_llm(role)


# ---- Emitter contract (required) ----

def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # ---- Optional tools (disabled by default) ----
    tool_set: Optional[ToolSet] = None

    # Example tool configuration (uncomment and customize):
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
        # Always keep trace (debug)
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            # ---- Build prompt tokens deterministically ----
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

            messages: List[Message] = [Message(role="user", content=prompt)]

            # ---- Resolve model + per-role params strictly (role-based deps) ----
            llm = deps.get_llm(ROLE_KEY)  # raises if missing
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format


            # ---- Stream events (Ollama capabilities: text, thinking, tools) ----
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
                    # Output content (or JSON payload). Do NOT put into thinking log.
                    text_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    # This is what goes into the UI thinking log.
                    span.thinking(ev.text)

                elif ev.type == "tool_call":
                    # Tools are part of the stream too; log them to thalamus log.
                    span.log(
                        level="info",
                        logger=f"runtime.nodes.{NODE_ID}",
                        message="tool_call",
                        fields={"name": ev.tool_call.name},
                    )

                elif ev.type == "tool_result" and ev.text:
                    span.log(
                        level="info",
                        logger=f"runtime.nodes.{NODE_ID}",
                        message="tool_result",
                        fields={"text": ev.text},
                    )

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            text = "".join(text_parts)

            # ---- Node-specific storage (choose one) ----
            #
            # Pattern A: store text for downstream nodes
            state.setdefault("runtime", {})[f"{NODE_ID}.text"] = text
            #
            # Pattern B: parse structured JSON (if this node is JSON-mode)
            # obj = json.loads(text)
            # state.setdefault("runtime", {})[f"{NODE_ID}.json"] = obj

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
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
