from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import chat_stream, ToolSet


# ---- Node metadata ----
#
# Conventions:
# - NODE_ID must match the module registration (and should match the graph node key).
# - ROLE_KEY must exist in cfg.llm.roles (deps.get_llm(ROLE_KEY) must succeed).
# - PROMPT_NAME must exist under resources/prompts/<PROMPT_NAME>.txt
#
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


def _parse_first_json_object(text: str) -> dict:
    """Parse the first JSON object found in `text`, tolerating trailing junk.

    Models sometimes emit extra whitespace or commentary even when JSON is requested.
    This keeps nodes resilient while still enforcing "first object wins".
    """
    s = (text or "").strip()

    # Strip common markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)

    # Start at first object brace.
    i = s.find("{")
    if i > 0:
        s = s[i:]

    obj, _idx = json.JSONDecoder().raw_decode(s)
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)

    # ---- Optional tools (preferred pattern: RuntimeToolkit policy) ----
    #
    # Use the toolkit to avoid ad-hoc ToolDef duplication. Tools are gated by:
    # - runtime.skills.registry.ENABLED_SKILLS
    # - runtime.tools.policy.node_skill_policy.NODE_ALLOWED_SKILLS[node_key]
    #
    # Example (enable tools for this node key):
    # tool_set = deps.services.tools.toolset_for_node(NODE_ID)
    #
    # NOTE: If you don't want tools, leave tool_set=None.
    #
    tool_set: Optional[ToolSet] = None

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
                    # Project-wide convention: prompts use <<TOKENS>> markers.
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

            # IMPORTANT (Ollama): tool calling and JSON-mode do not mix during the same round.
            # The tool loop handles this:
            # - tool rounds: response_format forced to None internally
            # - final formatting pass (no tools): response_format respected
            #
            for ev in chat_stream(
                provider=deps.provider,
                emitter=emitter,  # enables centralized tool-call logging
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
                    # Optional per-node tool call visibility (tool_loop also logs globally).
                    span.log(
                        level="info",
                        logger=f"runtime.nodes.{NODE_ID}",
                        message="tool_call",
                        fields={"name": ev.tool_call.name},
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
            # obj = _parse_first_json_object(text)
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
        role=ROLE_KEY,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
