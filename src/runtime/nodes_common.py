from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message, StreamEvent, ToolCall
from runtime.tool_loop import ToolSet, chat_stream


_TOKEN_RE = re.compile(r"<<([A-Z0-9_]+)>>")


# ----------------------------
# Small, stable primitives
# ----------------------------

def get_emitter(state: dict) -> TurnEmitter:
    em = (state.get("runtime") or {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def append_node_trace(state: dict, node_id: str) -> None:
    rt = state.setdefault("runtime", {})
    trace = rt.setdefault("node_trace", [])
    if isinstance(trace, list):
        trace.append(node_id)


def bump_counter(state: dict, key: str) -> int:
    rt = state.setdefault("runtime", {})
    try:
        rt[key] = int(rt.get(key) or 0) + 1
    except Exception:
        rt[key] = 1
    return int(rt[key])


def stable_json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def parse_first_json_object(text: str) -> dict:
    s = (text or "").strip()

    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)

    i = s.find("{")
    if i > 0:
        s = s[i:]

    obj, _ = json.JSONDecoder().raw_decode(s)
    if not isinstance(obj, dict):
        raise RuntimeError("output must be a JSON object")
    return obj


def _compact_text(text: str, *, limit: int = 2000) -> str:
    if text is None:
        return ""
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _compact_tool_args(tc: ToolCall, *, limit: int = 800) -> str:
    try:
        s = tc.arguments_json or ""
    except Exception:
        s = ""
    return _compact_text(s, limit=limit)


def collect_text(
    events: Iterable[StreamEvent],
    *,
    span=None,
    on_tool_result: Optional[Callable[[str, str], None]] = None,
    log_fields: Optional[dict] = None,
) -> str:
    """Collect final assistant text from a streamed chat.

    Also mirrors tool-call intent + tool results into the span log so that
    non-answer nodes have observable outputs in thalamus logs.
    """
    parts: list[str] = []
    pending_tool_names: list[str] = []

    for ev in events:
        if ev.type == "delta_text" and ev.text:
            parts.append(ev.text)
        elif ev.type == "delta_thinking" and ev.text and span is not None:
            try:
                span.thinking(ev.text)
            except Exception:
                pass
        elif ev.type == "tool_call" and ev.tool_call is not None:
            pending_tool_names.append(ev.tool_call.name)
            if span is not None:
                try:
                    span.log(
                        level="info",
                        logger="llm",
                        message=f"[llm] tool_call {ev.tool_call.name} args={_compact_tool_args(ev.tool_call)}",
                        fields={
                            "tool": ev.tool_call.name,
                            "tool_call_id": ev.tool_call.id,
                            "args_json": ev.tool_call.arguments_json,
                        },
                    )
                except Exception:
                    pass
        elif ev.type == "tool_result" and ev.text is not None:
            tool_name = pending_tool_names.pop(0) if pending_tool_names else "unknown_tool"
            if on_tool_result is not None:
                try:
                    on_tool_result(tool_name, ev.text)
                except Exception:
                    pass
            if span is not None:
                try:
                    span.log(
                        level="info",
                        logger="tool_loop",
                        message=f"[tool] result {tool_name} = {_compact_text(ev.text, limit=2000)}",
                        fields={"tool": tool_name, "result": ev.text},
                    )
                except Exception:
                    pass
        elif ev.type == "error":
            raise RuntimeError(ev.error or "LLM provider error")
        elif ev.type == "done":
            break

    out = "".join(parts)
    if span is not None:
        try:
            span.log(
                level="info",
                logger="llm",
                message=f"[llm] final_output = {_compact_text(out, limit=4000)}",
                fields={**({} if log_fields is None else dict(log_fields)), "final_output": out},
            )
        except Exception:
            pass
    return out


# ----------------------------
# Evidence packet helpers
# ----------------------------

def ensure_sources(ctx: dict) -> list[dict]:
    src = ctx.get("sources")
    if isinstance(src, list):
        out = [s for s in src if isinstance(s, dict)]
    else:
        out = []
    ctx["sources"] = out
    return out


def replace_source_by_kind(ctx: dict, *, kind: str, entry: dict) -> None:
    kind = (kind or "").strip()
    if not kind:
        return
    sources = ensure_sources(ctx)
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


def as_records(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ----------------------------
# Mechanical tool prefill (no LLM round)
# ----------------------------

def run_tools_mechanically(
    *,
    toolset: ToolSet,
    calls: Sequence[tuple[str, dict]],
    emitter: Optional[TurnEmitter] = None,
    node_id: Optional[str] = None,
    span_id: Optional[str] = None,
) -> list[Message]:
    """Execute tool handlers deterministically without a model tool_call."""
    out: list[Message] = []
    for idx, (name, args) in enumerate(calls, start=1):
        handler = toolset.handlers.get(name)
        if handler is None:
            continue

        if emitter is not None:
            try:
                args_compact = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                args_compact = "{}"
            if len(args_compact) > 400:
                args_compact = args_compact[:400] + "…"
            emitter.emit(
                emitter.factory.log_line(
                    level="info",
                    logger="tool_loop",
                    message=f"[tool] call {name} args={args_compact}",
                    node_id=node_id,
                    span_id=span_id,
                    fields={"tool": name, "args": args, "mechanical": True, "index": idx},
                )
            )

        try:
            result_obj = handler(args)

            if toolset.validators is not None:
                v = toolset.validators.get(name)
                if v is not None:
                    if isinstance(result_obj, str):
                        try:
                            parsed = json.loads(result_obj)
                        except Exception:
                            parsed = result_obj
                        v(parsed)
                    else:
                        v(result_obj)

            if isinstance(result_obj, str):
                result_text = result_obj
            else:
                result_text = json.dumps(result_obj, ensure_ascii=False)

        except Exception as e:
            if emitter is not None:
                emitter.emit(
                    emitter.factory.log_line(
                        level="error",
                        logger="tool_loop",
                        message=f"[tool] error {name}: {e}",
                        node_id=node_id,
                        span_id=span_id,
                        fields={"tool": name, "args": args, "mechanical": True, "error": str(e)},
                    )
                )
            result_text = json.dumps({"ok": False, "error": {"message": str(e)}}, ensure_ascii=False)

        out.append(Message(role="tool", name=name, tool_call_id=f"prefill_{idx}", content=result_text))
    return out


# ----------------------------
# Token builder system
# ----------------------------

@dataclass
class TokenSource:
    path: Optional[str] = None
    literal: Optional[str] = None
    inject: Optional[str] = None
    default: Any = ""
    transform: Optional[Callable[[Any], str]] = None


GLOBAL_TOKEN_SPEC: Dict[str, TokenSource] = {
    "USER_MESSAGE": TokenSource(path="task.user_text", transform=str),
    "WORLD_JSON": TokenSource(path="world", transform=stable_json),
    "TOPICS_JSON": TokenSource(path="world.topics", transform=lambda x: json.dumps(x or [], ensure_ascii=False)),
    "CONTEXT_JSON": TokenSource(path="context", transform=stable_json),
    "EXISTING_CONTEXT_JSON": TokenSource(path="context", transform=stable_json),
    "NOW_ISO": TokenSource(path="runtime.now_iso", transform=str),
    "NOW": TokenSource(path="runtime.now_iso", transform=str),
    "TIMEZONE": TokenSource(path="runtime.timezone", transform=str),
    "TZ": TokenSource(path="runtime.timezone", transform=str),
    "STATUS": TokenSource(path="runtime.status", transform=str),
    "ISSUES_JSON": TokenSource(path="runtime.issues", transform=stable_json),
    "ASSISTANT_ANSWER": TokenSource(path="final.answer", transform=str),
    "ASSISTANT_MESSAGE": TokenSource(path="final.answer", transform=str),
    "REQUESTED_LIMIT": TokenSource(path="context.memory_request.k", transform=str),
    "NODE_ID": TokenSource(inject="node_id"),
    "ROLE_KEY": TokenSource(inject="role_key"),
}


class TokenBuilder:
    """Centralized token resolution and rendering."""

    def __init__(self, state: dict, deps, node_id: str = "", role_key: str = ""):
        self.state = state
        self.deps = deps
        self.node_id = node_id
        self.role_key = role_key

    def _get_path(self, path: str) -> Any:
        cur: Any = self.state
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
            if cur is None:
                return None
        return cur

    def _extract_prompt_tokens(self, template: str) -> list[str]:
        return _TOKEN_RE.findall(template)

    def build_tokens(self, prompt_name: str) -> Dict[str, str]:
        template = self.deps.load_prompt(prompt_name)
        prompt_tokens = self._extract_prompt_tokens(template)

        tokens: Dict[str, str] = {}
        unresolved: list[str] = []

        for token_name in prompt_tokens:
            source = GLOBAL_TOKEN_SPEC.get(token_name)
            if source is None:
                unresolved.append(token_name)
                continue

            if source.literal is not None:
                value = source.literal
            elif source.inject == "node_id":
                value = self.node_id
            elif source.inject == "role_key":
                value = self.role_key
            elif source.path is not None:
                value = self._get_path(source.path)
                if value is None:
                    value = source.default
            else:
                value = source.default

            if source.transform is not None:
                value = source.transform(value)
            else:
                value = str(value) if value is not None else ""

            tokens[token_name] = value

        if unresolved:
            raise RuntimeError(
                f"Prompt '{prompt_name}' uses undefined tokens: {sorted(set(unresolved))}. "
                f"Add them to GLOBAL_TOKEN_SPEC in nodes_common.py"
            )

        return tokens

    def render_prompt(self, prompt_name: str) -> str:
        template = self.deps.load_prompt(prompt_name)
        tokens = self.build_tokens(prompt_name)
        return render_tokens(template, tokens)


# ----------------------------
# Canonical node runners
# ----------------------------

def run_streaming_answer_node(
    *,
    state: dict,
    deps,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    message_id: str,
) -> str:
    """Run the answer node with UI streaming via TurnEmitter."""
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)

    try:
        builder = TokenBuilder(state, deps, node_id, role_key)
        prompt = builder.render_prompt(prompt_name)
        llm = deps.get_llm(role_key)

        emitter.emit(emitter.factory.assistant_start(message_id=message_id))

        out_parts: list[str] = []
        for ev in chat_stream(
            provider=deps.provider,
            model=llm.model,
            messages=[Message(role="user", content=prompt)],
            params=llm.params,
            response_format=None,
            tools=None,
            max_steps=getattr(deps, "tool_step_limit", 6),
        ):
            if ev.type == "delta_text" and ev.text:
                out_parts.append(ev.text)
                emitter.emit(emitter.factory.assistant_delta(message_id=message_id, text=ev.text))
            elif ev.type == "delta_thinking" and ev.text:
                span.thinking(ev.text)
            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")
            elif ev.type == "done":
                break

        emitter.emit(emitter.factory.assistant_end(message_id=message_id))

        answer = " ".join(out_parts)
        span.end_ok()
        return answer
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise


def run_structured_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    node_key_for_tools: Optional[str] = None,
    response_format_override=None,
    tools_override=None,
    max_steps: Optional[int] = None,
    apply_result: Callable[[dict, dict], None],
) -> dict:
    """Run a single-pass node that returns a JSON object and applies it to state."""
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)

    try:
        builder = TokenBuilder(state, deps, node_id, role_key)
        prompt = builder.render_prompt(prompt_name)
        llm = deps.get_llm(role_key)

        toolset: Optional[ToolSet] = None
        if tools_override is not None:
            toolset = tools_override
        elif node_key_for_tools and services is not None and getattr(services, "tools", None) is not None:
            toolset = services.tools.toolset_for_node(node_key_for_tools)

        response_format = response_format_override if response_format_override is not None else llm.response_format

        events = chat_stream(
            provider=deps.provider,
            model=llm.model,
            messages=[Message(role="user", content=prompt)],
            params=llm.params,
            response_format=response_format,
            tools=toolset,
            max_steps=max_steps or getattr(deps, "tool_step_limit", 6),
            emitter=emitter,
            node_id=node_id,
            span_id=getattr(span, "span_id", None),
        )

        raw = collect_text(events, span=span)
        obj = parse_first_json_object(raw)
        apply_result(state, obj)

        span.end_ok()
        return state
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise


def run_controller_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    node_key_for_tools: str,
    apply_tool_result: Callable[[dict, str, str], None],
    apply_handoff: Callable[[dict, dict], bool],
    max_rounds: int = 5,
    max_steps: Optional[int] = None,
) -> dict:
    """Run a multi-round controller node."""
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)

    try:
        llm = deps.get_llm(role_key)
        toolset = services.tools.toolset_for_node(node_key_for_tools)
        builder = TokenBuilder(state, deps, node_id, role_key)

        for round_idx in range(1, max_rounds + 1):
            prompt = builder.render_prompt(prompt_name)
            messages = [Message(role="user", content=prompt)]

            events = chat_stream(
                provider=deps.provider,
                model=llm.model,
                messages=messages,
                params=llm.params,
                response_format=llm.response_format,
                tools=toolset,
                max_steps=max_steps or getattr(deps, "tool_step_limit", 6),
                emitter=emitter,
                node_id=node_id,
                span_id=getattr(span, "span_id", None),
            )

            raw = collect_text(
                events,
                span=span,
                on_tool_result=lambda tool_name, result_text: apply_tool_result(state, tool_name, result_text),
                log_fields={"round": round_idx},
            )

            obj = parse_first_json_object(raw)
            stop = apply_handoff(state, obj)
            if stop:
                break

        span.end_ok()
        return state
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise
