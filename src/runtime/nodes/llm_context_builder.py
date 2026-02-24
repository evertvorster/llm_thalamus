from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.state import State
from runtime.tool_loop import ToolSet, chat_stream


# ---- Node metadata ----
NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"     # resources/prompts/runtime_context_builder.txt
ROLE_KEY = "planner"                        # must exist in cfg.llm.roles

MAX_CONTEXT_ROUNDS = 5


def _get_emitter(state: State) -> TurnEmitter:
    em = (state.get("runtime") or {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _parse_first_json_object(text: str) -> dict:
    """Parse the first JSON object found in `text`, tolerating trailing junk."""
    s = (text or "").strip()

    # Strip common markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)

    i = s.find("{")
    if i > 0:
        s = s[i:]

    obj, _idx = json.JSONDecoder().raw_decode(s)
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


def _stable_json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _ctx_dict(state: State) -> Dict[str, Any]:
    ctx = state.get("context")
    if isinstance(ctx, dict):
        return ctx
    ctx = {}
    state["context"] = ctx
    return ctx


def _ensure_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    return []


def _replace_source_by_kind(state: State, src_obj: Dict[str, Any]) -> None:
    """Replace an entry in state['context']['sources'] by matching src_obj['kind']."""
    kind = src_obj.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return

    ctx = _ctx_dict(state)
    sources = _ensure_list(ctx.get("sources"))
    kind = kind.strip()

    new_sources: list[dict] = []
    replaced = False
    for s in sources:
        if isinstance(s, dict) and str(s.get("kind") or "").strip() == kind:
            new_sources.append(src_obj)
            replaced = True
        else:
            if isinstance(s, dict):
                new_sources.append(s)

    if not replaced:
        new_sources.append(src_obj)

    ctx["sources"] = new_sources


def _normalize_source_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both (kind,title,records,meta) and (kind,title,items,meta) shapes."""
    out = dict(obj)
    if "records" not in out and "items" in out:
        out["records"] = out.get("items")
    return out


def _apply_tool_result_to_context(*, state: State, tool_name: str, result_text: str) -> str | None:
    """Apply a tool_result payload to state['context'] with overwrite semantics.

    Tool handlers return a JSON object describing a single context 'source'.
    We replace any existing source of the same kind.

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

    obj = _normalize_source_shape(obj)
    if "kind" in obj and "records" in obj:
        _replace_source_by_kind(state, obj)
        return None

    return f"tool_result for {tool_name}: missing expected keys (kind/records)"


def _handoff_next(obj: Dict[str, Any]) -> str:
    v = obj.get("next")
    if isinstance(v, str) and v.strip():
        vv = v.strip().lower()
        if vv in ("answer", "memory_retriever", "planner"):
            return vv
    return "answer"


def make(deps: Deps, services) -> Callable[[State], State]:
    template = deps.load_prompt(PROMPT_NAME)
    toolset: Optional[ToolSet] = None
    if services is not None and getattr(services, "tools", None) is not None:
        toolset = services.tools.toolset_for_node("context_builder")

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)

        # Hop counter used by graph guard (graph checks runtime.context_hops).
        rt = state.setdefault("runtime", {})
        try:
            rt["context_hops"] = int(rt.get("context_hops") or 0) + 1
        except Exception:
            rt["context_hops"] = 1

        emitter = _get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            user_text = str((state.get("task") or {}).get("user_text", "") or "")
            world_json = _stable_json(state.get("world") or {})

            llm = deps.get_llm(ROLE_KEY)
            model = llm.model
            role_params = llm.params
            response_format = llm.response_format  # JSON-only handoff

            tool_apply_issues: list[str] = []

            for round_idx in range(1, MAX_CONTEXT_ROUNDS + 1):
                # Re-render prompt every round so the model sees tool-applied context updates.
                existing_context = state.get("context", {}) or {}
                if not isinstance(existing_context, dict):
                    existing_context = {}
                existing_context_json = _stable_json(existing_context)

                prompt = render_tokens(
                    template,
                    {
                        "USER_MESSAGE": user_text,
                        "WORLD_JSON": world_json,
                        "EXISTING_CONTEXT_JSON": existing_context_json,
                        "NODE_ID": NODE_ID,
                        "ROLE_KEY": ROLE_KEY,
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
                    max_steps=getattr(deps, "tool_step_limit", 6),
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
                    elif ev.type == "error":
                        raise RuntimeError(ev.error or "LLM provider error")
                    elif ev.type == "done":
                        break

                out_text = "".join(text_parts).strip()
                handoff = _parse_first_json_object(out_text)

                # Merge tool-application issues into handoff issues.
                issues = handoff.get("issues")
                issues_list: list[str] = []
                if isinstance(issues, list):
                    issues_list = [str(x) for x in issues if isinstance(x, (str, int, float, bool))]
                if tool_apply_issues:
                    issues_list.extend(tool_apply_issues)
                if issues_list:
                    handoff["issues"] = issues_list

                # Apply handoff to state (no sources are carried in handoff; tools already wrote them).
                ctx = _ctx_dict(state)

                if isinstance(handoff.get("complete"), bool):
                    ctx["complete"] = bool(handoff["complete"])

                ctx["next"] = _handoff_next(handoff)

                # Optional scratch notes (internal only).
                if isinstance(handoff.get("notes"), str):
                    ctx["notes"] = handoff.get("notes") or ""

                # Optional: memory_request planning directive for memory_retriever.
                # This is NOT a tool result; it's a controller instruction.
                mr = handoff.get("memory_request")
                if isinstance(mr, dict):
                    q = mr.get("query")
                    k = mr.get("k")
                    if isinstance(q, str) and q.strip():
                        out_mr: dict[str, Any] = {"query": q.strip()}
                        try:
                            kk = int(k)
                            if 1 <= kk <= 16:
                                out_mr["k"] = kk
                        except Exception:
                            pass
                        ctx["memory_request"] = out_mr

                # If model says complete or wants to hand off, exit loop.
                # If tools were called, the prompt expects re-run; we are doing that by looping.
                if bool(ctx.get("complete")) or ctx.get("next") in ("answer", "planner", "memory_retriever"):
                    break

            # Default safe behavior: if no directive, answer.
            ctx = _ctx_dict(state)
            if not isinstance(ctx.get("next"), str) or not str(ctx.get("next") or "").strip():
                ctx["next"] = "answer"

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
