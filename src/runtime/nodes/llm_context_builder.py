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

MAX_CONTEXT_ROUNDS = 5


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


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _ctx_sources(state: State) -> list[dict[str, Any]]:
    ctx = state.setdefault("context", {})
    if not isinstance(ctx, dict):
        ctx = {}
        state["context"] = ctx
    sources = ctx.setdefault("sources", [])
    if not isinstance(sources, list):
        sources = []
        ctx["sources"] = sources
    # Normalize to list[dict]
    out: list[dict[str, Any]] = []
    for x in sources:
        if isinstance(x, dict):
            out.append(x)
    ctx["sources"] = out
    return out


def _replace_source_by_kind(state: State, src_obj: dict[str, Any]) -> None:
    kind = src_obj.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return
    kind = kind.strip()
    sources = _ctx_sources(state)
    sources = [s for s in sources if not (isinstance(s, dict) and s.get("kind") == kind)]
    sources.append(src_obj)
    state["context"]["sources"] = sources  # type: ignore[index]


def _apply_tool_result_to_context(*, state: State, tool_name: str, result_text: str) -> str | None:
    """Apply a tool_result payload to state['context'] with overwrite semantics.

    Tool handlers in this project return a single JSON object that already matches
    the SOURCE ENTRY SHAPE (kind/title/records[/meta]).
    We simply replace any existing source of the same kind.

    Returns an issue string if the result could not be applied.
    """
    obj = _safe_json_loads(result_text)
    if not isinstance(obj, dict):
        return f"tool_result for {tool_name}: non-JSON or non-object result"

    # If the tool returned an ok/error envelope, surface it.
    ok = obj.get("ok")
    if ok is False:
        err = obj.get("error")
        return f"tool_result for {tool_name}: ok=false error={err!r}"

    if "kind" in obj and "records" in obj:
        _replace_source_by_kind(state, obj)
        return None

    # Some tools may return other shapes; don't silently drop.
    return f"tool_result for {tool_name}: missing expected keys (kind/records)"



def _get_next_handoff(obj: Dict[str, Any]) -> str:
    v = obj.get("next")
    if isinstance(v, str) and v.strip():
        vv = v.strip().lower()
        if vv in ("answer", "planner"):
            return vv
    return "answer"



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

            prompt = ""  # rendered per round (EXISTING_CONTEXT_JSON is mutable)
            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format

            last_handoff: dict[str, Any] | None = None
            tool_apply_issues: list[str] = []

            for round_idx in range(1, MAX_CONTEXT_ROUNDS + 1):
                span.thinking(f"\n\n=== CONTEXT BUILDER ROUND {round_idx}/{MAX_CONTEXT_ROUNDS} ===\n")

                # Re-render prompt every round so the model sees tool-applied context updates.
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

                messages: List[Message] = [Message(role="user", content=prompt)]

                text_parts: list[str] = []
                pending_tool_names: list[str] = []

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
                    elif ev.type == "tool_call" and ev.tool_call:
                        pending_tool_names.append(ev.tool_call.name)
                    elif ev.type == "tool_result" and ev.text is not None:
                        tool_name = pending_tool_names.pop(0) if pending_tool_names else "unknown_tool"
                        issue = _apply_tool_result_to_context(
                            state=state, tool_name=tool_name, result_text=ev.text
                        )
                        if issue:
                            tool_apply_issues.append(issue)
                            span.log(
                                level="warning",
                                logger="runtime.nodes.context_builder",
                                message="context_builder tool_result not applied",
                                fields={"issue": issue, "tool_name": tool_name},
                            )
                    elif ev.type == "error":
                        raise RuntimeError(ev.error or "LLM provider error")
                    elif ev.type == "done":
                        break

                out_text = "".join(text_parts).strip()

                try:
                    handoff = _parse_first_json_object(out_text)
                except Exception:
                    span.log(
                        level="error",
                        logger="runtime.nodes.context_builder",
                        message="context_builder parse error",
                        fields={"raw_preview": out_text[:2000]},
                    )
                    raise

                # Merge any tool-application issues into the handoff issues list.
                issues = handoff.get("issues")
                if not isinstance(issues, list):
                    issues = []
                    handoff["issues"] = issues
                for s in tool_apply_issues:
                    issues.append(s)
                tool_apply_issues = []

                last_handoff = handoff

                complete = bool(handoff.get("complete", False))
                next_handoff = _get_next_handoff(handoff)
                issues_n = len(_ensure_list(handoff.get("issues")))

                span.thinking(
                    "=== CONTEXT BUILDER ROUND RESULT ===\n"
                    f"complete={complete!r} next={next_handoff!r} issues_n={issues_n!r}\n"
                )

                # Optional: allow model to set/update notes in durable context.
                notes = handoff.get("notes")
                if isinstance(notes, str):
                    ctx = state.setdefault("context", {})
                    if isinstance(ctx, dict):
                        ctx["notes"] = notes

                if complete:
                    break

            if last_handoff is None:
                raise RuntimeError("context_builder: no output produced")

            if not bool(last_handoff.get("complete", False)):
                issues = last_handoff.get("issues")
                if isinstance(issues, list):
                    issues.append(f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true")
                else:
                    last_handoff["issues"] = [f"context_builder: reached max rounds ({MAX_CONTEXT_ROUNDS}) without complete=true"]

            # Runtime-only status / routing signals (not durable context).
            rt = state.setdefault("runtime", {})
            rt["context_builder_complete"] = bool(last_handoff.get("complete", False))
            rt["context_builder_next"] = _get_next_handoff(last_handoff)

            sources = _ctx_sources(state)
            rt["context_builder_status"] = "ok" if len(sources) > 0 else "insufficient_data"
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