from __future__ import annotations

import json
from typing import Callable

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.world_modifier"
GROUP = "llm"
LABEL = "World Modifier"
PROMPT_NAME = "runtime_world_modifier"  # resources/prompts/runtime_world_modifier.txt
ROLE_KEY = "planner"  # tool-using node


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str(state.get("task", {}).get("user_text", "") or "")

            world_json = json.dumps(
                state.get("world", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                },
            )

            # Tool exposure is keyed by the graph node key ("world_modifier"), not NODE_ID.
            toolset = services.tools.toolset_for_node("world_modifier")

            llm = deps.get_llm(ROLE_KEY)
            raw_parts: list[str] = []
            last_tool_result_text: str | None = None

            for ev in chat_stream(
                provider=deps.provider,
                model=llm.model,
                messages=[Message(role="user", content=prompt)],
                params=llm.params,
                # IMPORTANT: tools enabled => do not force response_format during tool rounds.
                response_format=None,
                tools=toolset,
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    # This node outputs structured JSON; keep it out of thinking.
                    raw_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)

                elif ev.type == "tool_call":
                    span.log(
                        level="info",
                        logger=f"runtime.nodes.{NODE_ID}",
                        message="tool_call",
                        fields={"name": ev.tool_call.name},
                    )

                elif ev.type == "tool_result" and ev.text:
                    last_tool_result_text = ev.text
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

            raw_text = "".join(raw_parts).strip()
            if not raw_text:
                raise RuntimeError("world_modifier: empty model output")

            obj = json.loads(raw_text)
            if not isinstance(obj, dict):
                raise RuntimeError("world_modifier: output must be a JSON object")

            # If we saw a tool result, treat it as authoritative and update in-memory state.
            # This ensures the answer node sees the updated world in the same turn.
            if last_tool_result_text:
                try:
                    tool_obj = json.loads(last_tool_result_text)
                    if isinstance(tool_obj, dict) and isinstance(tool_obj.get("world"), dict):
                        state["world"] = tool_obj["world"]
                except Exception as e:
                    span.log(
                        level="info",
                        logger=f"runtime.nodes.{NODE_ID}",
                        message="tool_result_parse_failed",
                        fields={"error": str(e)},
                    )

            # Store structured result for debugging/inspection (optional, harmless).
            state.setdefault("runtime", {})["world_modifier"] = obj

            # Provide a short status string for downstream prompt framing.
            summary = str(obj.get("summary", "") or "").strip()
            if summary:
                state.setdefault("runtime", {})["status"] = summary

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
