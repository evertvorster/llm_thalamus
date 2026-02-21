from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

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


def _ensure_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    return []


def _merge_notes(old: str, new: str) -> str:
    old = (old or "").strip()
    new = (new or "").strip()
    if not old:
        return new
    if not new:
        return old
    if new in old:
        return old
    return old + "\n" + new


def _merge_context_obj(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge incoming context_builder output into existing state['context'].

    Append/merge semantics (builder, not replacer):
    - issues: extend
    - context.sources: extend
    - context.notes: append text with newline
    - other keys: last-write-wins, but unknown keys are preserved
    """
    out: Dict[str, Any] = dict(existing or {})

    # Merge 'issues'
    if "issues" in incoming:
        old_issues = _ensure_list(out.get("issues"))
        new_issues = _ensure_list(incoming.get("issues"))
        out["issues"] = old_issues + new_issues

    # Merge nested 'context'
    inc_ctx = incoming.get("context")
    if isinstance(inc_ctx, dict):
        old_ctx = out.get("context")
        if not isinstance(old_ctx, dict):
            old_ctx = {}
        merged_ctx = dict(old_ctx)

        # sources
        old_sources = _ensure_list(merged_ctx.get("sources"))
        new_sources = _ensure_list(inc_ctx.get("sources"))
        merged_ctx["sources"] = old_sources + new_sources

        # notes
        merged_ctx["notes"] = _merge_notes(
            str(merged_ctx.get("notes", "") or ""),
            str(inc_ctx.get("notes", "") or ""),
        )

        # Preserve any other nested keys in incoming.context (shallow)
        for k, v in inc_ctx.items():
            if k in ("sources", "notes"):
                continue
            merged_ctx[k] = v

        out["context"] = merged_ctx

    # Merge top-level keys (preserve unknown keys; apply last-write-wins for scalars)
    for k, v in incoming.items():
        if k in ("issues", "context"):
            continue
        out[k] = v

    return out


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

            existing_context = state.get("context", {}) or {}
            if not isinstance(existing_context, dict):
                existing_context = {}
            existing_context_json = json.dumps(existing_context, ensure_ascii=False, sort_keys=True)

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "WORLD_JSON": world_json,
                    "EXISTING_CONTEXT_JSON": existing_context_json,
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
                sources_n = len(
                    _ensure_list(
                        (
                            (ctx_obj.get("context") or {})
                            if isinstance(ctx_obj.get("context"), dict)
                            else {}
                        ).get("sources")
                    )
                )
                issues_n = len(_ensure_list(ctx_obj.get("issues")))

                span.thinking(
                    "=== CONTEXT BUILDER ROUND RESULT ===\n"
                    f"complete={complete!r} sources_n={sources_n!r} issues_n={issues_n!r}\n"
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
                            "Preserve existing sources; append new sources only. "
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
                    issues.append(
                        f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true"
                    )
                else:
                    last_ctx_obj["issues"] = [
                        f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true"
                    ]

            # Merge onto state for downstream nodes (builder, not replacer).
            existing_context = state.get("context", {}) or {}
            if not isinstance(existing_context, dict):
                existing_context = {}
            state["context"] = _merge_context_obj(existing_context, last_ctx_obj)

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