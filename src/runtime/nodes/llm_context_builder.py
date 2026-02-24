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


NODE_ID = "llm.context_builder"
GROUP = "llm"
LABEL = "Context Builder"
PROMPT_NAME = "runtime_context_builder"
ROLE_KEY = "planner"

MAX_CONTEXT_ROUNDS = 5


def _get_emitter(state: State) -> TurnEmitter:
    em = (state.get("runtime") or {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _parse_first_json_object(text: str) -> dict:
    s = (text or "").strip()

    # Strip common markdown fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)

    # Find first '{'
    i = s.find("{")
    if i > 0:
        s = s[i:]

    obj, _ = json.JSONDecoder().raw_decode(s)
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


def _ensure_sources(ctx: Dict[str, Any]) -> list[dict]:
    src = ctx.get("sources")
    if isinstance(src, list):
        out = [s for s in src if isinstance(s, dict)]
    else:
        out = []
    ctx["sources"] = out
    return out


def _replace_source(ctx: Dict[str, Any], *, kind: str, entry: dict) -> None:
    kind = kind.strip()
    if not kind:
        return
    sources = _ensure_sources(ctx)

    new_sources: list[dict] = []
    replaced = False
    for s in sources:
        if str(s.get("kind") or "").strip() == kind:
            new_sources.append(entry)
            replaced = True
        else:
            new_sources.append(s)
    if not replaced:
        new_sources.append(entry)
    ctx["sources"] = new_sources


def _as_records(value: Any) -> list:
    """Normalize arbitrary tool payload into records[]."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    # dict / scalar -> single record
    return [value]


def _apply_tool_result(state: State, *, tool_name: str, result_text: str) -> Optional[str]:
    """Apply tool result into state['context']['sources'] with replacement semantics.

    We do NOT rely on handlers returning a particular shape. We wrap results into our
    canonical source entry form by tool_name.
    """
    ctx = _ctx_dict(state)

    try:
        payload = json.loads(result_text) if result_text else {}
    except Exception as e:
        return f"{tool_name}: tool result was not valid JSON ({e})"

    # If handler returned an error envelope, surface it.
    if isinstance(payload, dict) and payload.get("ok") is False:
        return f"{tool_name}: tool error {payload.get('error')!r}"

    if tool_name == "chat_history_tail":
        # Tool def says it returns {kind,title,items,meta}. We normalize to records[].
        if isinstance(payload, dict):
            items = payload.get("items")
            title = payload.get("title") if isinstance(payload.get("title"), str) else "Recent chat turns"
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            entry = {
                "kind": "chat_turns",
                "title": title,
                "records": _as_records(items),
                "meta": meta,
            }
        else:
            entry = {
                "kind": "chat_turns",
                "title": "Recent chat turns",
                "records": _as_records(payload),
                "meta": {},
            }
        _replace_source(ctx, kind="chat_turns", entry=entry)
        return None

    if tool_name == "memory_query":
        # We store the raw payload as records[]; Answer can interpret.
        entry = {
            "kind": "memories",
            "title": "Memory candidates",
            "records": _as_records(payload),
            "meta": {},
        }
        _replace_source(ctx, kind="memories", entry=entry)
        return None

    # Unknown tool name: store as generic tool_result
    entry = {
        "kind": "tool_result",
        "title": f"Tool result: {tool_name}",
        "records": _as_records(payload),
        "meta": {},
    }
    _replace_source(ctx, kind="tool_result", entry=entry)
    return None


def _handoff_next(obj: Dict[str, Any]) -> str:
    v = obj.get("next")
    if isinstance(v, str):
        vv = v.strip()
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
            params = llm.params
            response_format = llm.response_format  # JSON for handoff

            pending_tool_names: list[str] = []
            tool_apply_issues: list[str] = []

            for _round in range(1, MAX_CONTEXT_ROUNDS + 1):
                existing_context = state.get("context") or {}
                if not isinstance(existing_context, dict):
                    existing_context = {}
                prompt = render_tokens(
                    template,
                    {
                        "USER_MESSAGE": user_text,
                        "WORLD_JSON": world_json,
                        "EXISTING_CONTEXT_JSON": _stable_json(existing_context),
                        "NODE_ID": NODE_ID,
                        "ROLE_KEY": ROLE_KEY,
                    },
                )

                messages: List[Message] = [Message(role="user", content=prompt)]
                text_parts: list[str] = []

                for ev in chat_stream(
                    provider=deps.provider,
                    model=model,
                    messages=messages,
                    params=params,
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
                        issue = _apply_tool_result(state, tool_name=tool_name, result_text=ev.text)
                        if issue:
                            tool_apply_issues.append(issue)
                    elif ev.type == "error":
                        raise RuntimeError(ev.error or "LLM provider error")
                    elif ev.type == "done":
                        break

                handoff = _parse_first_json_object("".join(text_parts))

                ctx = _ctx_dict(state)
                if isinstance(handoff.get("complete"), bool):
                    ctx["complete"] = bool(handoff["complete"])
                ctx["next"] = _handoff_next(handoff)

                # Issues: merge tool apply issues + model issues.
                issues_out: list[str] = []
                if isinstance(handoff.get("issues"), list):
                    issues_out.extend([str(x) for x in handoff["issues"]])
                issues_out.extend(tool_apply_issues)
                if issues_out:
                    ctx["issues"] = issues_out

                if isinstance(handoff.get("notes"), str):
                    ctx["notes"] = handoff.get("notes") or ""

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

                # Exit policy:
                # - if complete, stop
                # - if next is answer/planner/memory_retriever, stop (handoff decision made)
                if bool(ctx.get("complete")) or ctx.get("next") in ("answer", "planner", "memory_retriever"):
                    break

            # Default-safe route
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
