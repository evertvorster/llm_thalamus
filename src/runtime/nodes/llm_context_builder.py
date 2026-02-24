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

MAX_CONTEXT_ROUNDS = 3


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _ensure_list(v: Any) -> list:
    return v if isinstance(v, list) else []


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


def _parse_first_json_object(raw: str) -> dict[str, Any]:
    if not raw:
        raise RuntimeError("context_builder: empty model output")

    s = raw.strip()

    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
            s = "\n".join(lines[1:-1]).strip()

    start = s.find("{")
    if start < 0:
        raise RuntimeError(f"context_builder: no JSON object found in output: {raw!r}")

    depth = 0
    end = -1
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        raise RuntimeError(f"context_builder: unterminated JSON object: {raw!r}")

    obj_text = s[start:end]

    try:
        obj = json.loads(obj_text)
    except Exception as e:
        raise RuntimeError(f"context_builder: JSON parse failed: {e}") from e

    if not isinstance(obj, dict):
        raise RuntimeError("context_builder: output must be a JSON object")

    return obj


def _merge_context_obj(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(existing or {})

    if "issues" in incoming:
        old_issues = _ensure_list(out.get("issues"))
        new_issues = _ensure_list(incoming.get("issues"))
        out["issues"] = old_issues + new_issues

    inc_ctx = incoming.get("context")
    if isinstance(inc_ctx, dict):
        old_ctx = out.get("context")
        if not isinstance(old_ctx, dict):
            old_ctx = {}
        merged_ctx = dict(old_ctx)

        old_sources = _ensure_list(merged_ctx.get("sources"))
        new_sources = _ensure_list(inc_ctx.get("sources"))

        # Optional replacement semantics for sources.
        #
        # This enables the context builder to "back-track" by replacing prior sources with a
        # refined subset (copy/paste), without summarization.
        #
        # Controls (all optional; default is append-only):
        #   inc_ctx["sources_mode"]: "append" (default) | "replace_all" | "replace"
        #   inc_ctx["replace_kinds"]: ["chat_turns", "memories", ...]  -> remove old sources whose "kind" matches
        #   inc_ctx["replace_titles"]: ["Recent chat turns", ...]     -> remove old sources whose "title" matches
        #
        # Notes:
        # - "replace_all" drops all prior sources and uses only new_sources.
        # - "replace" drops only matching kinds/titles; all other old sources are preserved.
        # - If replace_kinds/titles are provided without sources_mode, we treat it as "replace".
        mode = str(inc_ctx.get("sources_mode") or "").strip().lower()
        replace_kinds = inc_ctx.get("replace_kinds")
        replace_titles = inc_ctx.get("replace_titles")

        rk: set[str] = set()
        rt: set[str] = set()

        if isinstance(replace_kinds, list):
            for x in replace_kinds:
                if isinstance(x, str) and x.strip():
                    rk.add(x.strip())

        if isinstance(replace_titles, list):
            for x in replace_titles:
                if isinstance(x, str) and x.strip():
                    rt.add(x.strip())

        if (rk or rt) and not mode:
            mode = "replace"

        if mode == "replace_all":
            merged_ctx["sources"] = list(new_sources)
        elif mode == "replace":
            filtered: list = []
            for s in old_sources:
                if not isinstance(s, dict):
                    filtered.append(s)
                    continue
                k = s.get("kind")
                t = s.get("title")
                if (isinstance(k, str) and k in rk) or (isinstance(t, str) and t in rt):
                    continue
                filtered.append(s)
            merged_ctx["sources"] = filtered + list(new_sources)
        else:
            # Default: append-only
            merged_ctx["sources"] = old_sources + list(new_sources)

        merged_ctx["notes"] = _merge_notes(
            str(merged_ctx.get("notes", "") or ""),
            str(inc_ctx.get("notes", "") or ""),
        )

        for k, v in inc_ctx.items():
            if k in ("sources", "notes"):
                continue
            merged_ctx[k] = v

        out["context"] = merged_ctx

    for k, v in incoming.items():
        if k in ("issues", "context"):
            continue
        out[k] = v

    return out


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)
    toolset = services.tools.toolset_for_node("context_builder")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
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
                    ctx_obj = _parse_first_json_object(out_text)
                except Exception:
                    span.log(
                        level="error",
                        logger="runtime.nodes.context_builder",
                        message="context_builder parse error",
                        fields={"raw_preview": out_text[:2000]},
                    )
                    raise

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