from __future__ import annotations

import json
from typing import Callable, List

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"  # must exist in cfg.llm.roles

# Targeted: bounded recursion for context refinement
MAX_CONTEXT_ROUNDS = 3


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # LangGraph node key is "context_builder" (see graph_build.py)
    toolset = services.tools.toolset_for_node("context_builder")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            # DEBUG: log tools exposed to this node
            try:
                tool_names = [t.name for t in (toolset.defs or [])]
            except Exception:
                tool_names = []
            span.thinking(
                "\n\n=== CONTEXT BUILDER DEBUG: TOOLS EXPOSED ===\n"
                f"tool_defs_n={len(tool_names)} tool_names={tool_names}\n"
            )

            user_text = str(state.get("task", {}).get("user_text", "") or "")
            world = state.get("world", {}) or {}
            world_json = json.dumps(world, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                },
            )

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format

            # Conversation for the context builder across rounds.
            messages: List[Message] = [Message(role="user", content=prompt)]

            last_ctx_obj: dict | None = None

            for round_idx in range(1, MAX_CONTEXT_ROUNDS + 1):
                span.thinking(f"\n\n=== CONTEXT BUILDER ROUND {round_idx}/{MAX_CONTEXT_ROUNDS} ===\n")

                text_parts: list[str] = []
                for ev in chat_stream(
                    provider=deps.provider,
                    model=model,
                    messages=messages,
                    params=role_params,
                    response_format=response_format,
                    tools=toolset,
                    max_steps=deps.tool_step_limit,
                    emitter=emitter,
                    node_id=span.node_id,
                    span_id=span.span_id,
                ):
                    if ev.type == "delta_text" and ev.text:
                        text_parts.append(ev.text)
                    elif ev.type == "delta_thinking" and ev.text:
                        span.thinking(ev.text)
                    elif ev.type == "error":
                        raise RuntimeError(ev.error or "LLM provider error")
                    elif ev.type == "done":
                        break

                out_text = "".join(text_parts).strip()
                try:
                    ctx_obj = json.loads(out_text)
                except Exception as e:
                    raise RuntimeError(f"context_builder: output not valid JSON: {e}") from e

                if not isinstance(ctx_obj, dict):
                    raise RuntimeError("context_builder: output must be a JSON object")

                last_ctx_obj = ctx_obj

                complete = bool(ctx_obj.get("complete", False))
                requested_n = (ctx_obj.get("chat") or {}).get("requested_n")
                used_n = (ctx_obj.get("chat") or {}).get("used_n")
                turns_n = len(((ctx_obj.get("chat") or {}).get("turns") or []) or [])

                span.thinking(
                    "=== CONTEXT BUILDER ROUND RESULT ===\n"
                    f"complete={complete!r} requested_n={requested_n!r} used_n={used_n!r} turns_n={turns_n!r}\n"
                )

                if complete:
                    break

                # Not complete: add the model output and ask it to continue refining.
                # Keep this minimal; the system prompt already defines the schema.
                messages.append(Message(role="assistant", content=out_text))
                messages.append(
                    Message(
                        role="user",
                        content=(
                            "Continue refining the CONTEXT JSON. "
                            "If you need more chat turns to resolve references, call chat_history_tail "
                            "with the smallest limit that will help. "
                            "Return ONE JSON object only."
                        ),
                    )
                )

            if last_ctx_obj is None:
                raise RuntimeError("context_builder: no output produced")

            # If we exhausted rounds without completion, surface that as an issue.
            if not bool(last_ctx_obj.get("complete", False)):
                issues = last_ctx_obj.get("issues")
                if isinstance(issues, list):
                    issues.append(f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true")
                else:
                    last_ctx_obj["issues"] = [f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true"]

            # Store on state for downstream nodes.
            state["context"] = last_ctx_obj

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
        role=ROLE_KEY,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
