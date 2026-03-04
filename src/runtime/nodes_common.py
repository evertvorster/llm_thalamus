from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from runtime.prompting import render_tokens
from runtime.providers.types import Message, StreamEvent
from runtime.tool_loop import ToolSet, chat_stream
from runtime.emitter import TurnEmitter


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

    # Strip markdown code fences
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


def collect_text(events: Iterable[StreamEvent], *, span=None) -> str:
    parts: list[str] = []
    for ev in events:
        if ev.type == "delta_text" and ev.text:
            parts.append(ev.text)
        elif ev.type == "delta_thinking" and ev.text and span is not None:
            try:
                span.thinking(ev.text)
            except Exception:
                pass
        elif ev.type == "error":
            raise RuntimeError(ev.error or "LLM provider error")
        elif ev.type == "done":
            break
    return "".join(parts)


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
# Canonical node runners
# ----------------------------

def run_structured_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    tokens: Dict[str, str],
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
        template = deps.load_prompt(prompt_name)
        prompt = render_tokens(template, tokens)

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


def run_streaming_answer_node(
    *,
    state: dict,
    deps,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    tokens: Optional[Dict[str, str]] = None,  # Made optional (legacy support)
    message_id: str,
) -> str:
    """Run the answer node with UI streaming via TurnEmitter."""
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)
    try:
        # Use TokenBuilder (global spec) or legacy tokens dict
        if tokens is not None:
            # Legacy path
            template = deps.load_prompt(prompt_name)
            prompt = render_tokens(template, tokens)
        else:
            # Global spec path
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
            response_format=None,   # stream plain text
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
    tokens_for_round: Callable[[dict, int], Dict[str, str]],
    apply_tool_result: Callable[[dict, str, str], None],
    apply_handoff: Callable[[dict, dict], bool],
    max_rounds: int = 5,
    max_steps: Optional[int] = None,
) -> dict:
    """Run a multi-round controller node.

    - Re-renders prompt every round (so state changes are visible).
    - Allows tools and forwards tool_result payloads to apply_tool_result(state, tool_name, result_text).
    - After each round, parses the model JSON handoff and calls apply_handoff(state, obj).
      If apply_handoff returns True, stop early.
    """
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)

    try:
        template = deps.load_prompt(prompt_name)
        llm = deps.get_llm(role_key)
        toolset = services.tools.toolset_for_node(node_key_for_tools)

        for round_idx in range(1, max_rounds + 1):
            tokens = tokens_for_round(state, round_idx)
            prompt = render_tokens(template, tokens)
            messages = [Message(role="user", content=prompt)]

            text_parts: list[str] = []
            pending_tool_names: list[str] = []

            for ev in chat_stream(
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
            ):
                if ev.type == "delta_text" and ev.text:
                    text_parts.append(ev.text)
                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)
                elif ev.type == "tool_call" and ev.tool_call:
                    pending_tool_names.append(ev.tool_call.name)
                elif ev.type == "tool_result" and ev.text is not None:
                    tool_name = pending_tool_names.pop(0) if pending_tool_names else "unknown_tool"
                    apply_tool_result(state, tool_name, ev.text)
                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")
                elif ev.type == "done":
                    break

            obj = parse_first_json_object("".join(text_parts))
            stop = apply_handoff(state, obj)
            if stop:
                break

        span.end_ok()
        return state
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise


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
    """Execute tool handlers deterministically without a model tool_call.

    Returns tool messages that you can include in a messages list if needed.
    """
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
            # New tool contract: handlers accept parsed args objects (dict) and return
            # a JSON-serializable object or a string. Normalize here to a string for Message.content.
            result_obj = handler(args)

            # Optional per-tool validators.
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
# ============================================================================
# Token Builder System (Centralized Token Resolution)
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import re

_TOKEN_RE = re.compile(r"<<([A-Z0-9_]+)>>")

@dataclass
class TokenSource:
    """Defines where a token value comes from."""
    path: Optional[str] = None        # e.g., "task.user_text", "world.topics"
    literal: Optional[str] = None     # Fixed value (resolved per-node)
    inject: Optional[str] = None      # Runtime-injected (e.g., "node_id", "role_key")
    default: Any = ""
    transform: Optional[Callable[[Any], str]] = None  # e.g., stable_json

# ============================================================================
# GLOBAL TOKEN SPECIFICATION (Single Source of Truth)
# ============================================================================

GLOBAL_TOKEN_SPEC: Dict[str, TokenSource] = {
    # === User Input ===
    "USER_MESSAGE": TokenSource(path="task.user_text", transform=str),
    
    # === World State ===
    "WORLD_JSON": TokenSource(path="world", transform=stable_json),
    "TOPICS_JSON": TokenSource(path="world.topics", transform=lambda x: json.dumps(x or [], ensure_ascii=False)),
    
    # === Context ===
    "CONTEXT_JSON": TokenSource(path="context", transform=stable_json),
    "EXISTING_CONTEXT_JSON": TokenSource(path="context", transform=stable_json),  # Alias for backward compat
    
    # === Runtime/Time ===
    "NOW_ISO": TokenSource(path="runtime.now_iso", transform=str),
    "NOW": TokenSource(path="runtime.now_iso", transform=str),  # Alias for backward compat
    "TIMEZONE": TokenSource(path="runtime.timezone", transform=str),
    "TZ": TokenSource(path="runtime.timezone", transform=str),  # Alias for backward compat
    
    # === Status/Issues ===
    "STATUS": TokenSource(path="runtime.status", transform=str),
    "ISSUES_JSON": TokenSource(path="runtime.issues", transform=stable_json),
    
    # === Final/Answer ===
    "ASSISTANT_ANSWER": TokenSource(path="final.answer", transform=str),
    "ASSISTANT_MESSAGE": TokenSource(path="final.answer", transform=str),  # Alias for backward compat
    
    # === Memory ===
    "REQUESTED_LIMIT": TokenSource(path="context.memory_request.k", transform=str),
    
    # === Per-Node Literals (injected at render time) ===
    "NODE_ID": TokenSource(inject="node_id"),
    "ROLE_KEY": TokenSource(inject="role_key"),
}

# ============================================================================
# Token Builder (Auto-Resolves Prompt Tokens Against Global Spec)
# ============================================================================

class TokenBuilder:
    """Centralized token resolution and rendering."""

    def __init__(self, state: dict, deps, node_id: str = "", role_key: str = ""):
        self.state = state
        self.deps = deps
        self.node_id = node_id
        self.role_key = role_key

    def _get_path(self, path: str) -> Any:
        """Resolve a dotted path against state."""
        if path.startswith("world."):
            key = path[6:]
            return self.state.get("world", {}).get(key)
        elif path.startswith("runtime."):
            key = path[8:]
            return self.state.get("runtime", {}).get(key)
        elif path.startswith("context."):
            key = path[8:]
            return self.state.get("context", {}).get(key)
        elif path.startswith("task."):
            key = path[5:]
            return self.state.get("task", {}).get(key)
        elif path.startswith("final."):
            key = path[6:]
            return self.state.get("final", {}).get(key)
        else:
            return self.state.get(path)

    def _extract_prompt_tokens(self, template: str) -> List[str]:
        """Extract all <<TOKEN>> placeholders from template."""
        return _TOKEN_RE.findall(template)

    def build_tokens(self, prompt_name: str) -> Dict[str, str]:
        """Build token dict by resolving prompt tokens against global spec."""
        template = self.deps.load_prompt(prompt_name)
        prompt_tokens = self._extract_prompt_tokens(template)
        
        tokens = {}
        unresolved = []
        
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

            if source.transform:
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
        """Load prompt and render tokens."""
        template = self.deps.load_prompt(prompt_name)
        tokens = self.build_tokens(prompt_name)
        return render_tokens(template, tokens)

# ============================================================================
# Updated Runner Functions (Use Global Spec Automatically)
# ============================================================================

def run_structured_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    tokens: Optional[Dict[str, str]] = None,  # Legacy (deprecated)
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
        # Use TokenBuilder (global spec) or legacy tokens dict
        if tokens is not None:
            # Legacy path
            template = deps.load_prompt(prompt_name)
            prompt = render_tokens(template, tokens)
        else:
            # Global spec path
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
    tokens_for_round: Optional[Callable[[dict, int], Dict[str, str]]] = None,  # Legacy
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

        for round_idx in range(1, max_rounds + 1):
            # Use TokenBuilder (global spec) or legacy tokens_for_round
            if tokens_for_round is not None:
                tokens = tokens_for_round(state, round_idx)
                template = deps.load_prompt(prompt_name)
                prompt = render_tokens(template, tokens)
            else:
                builder = TokenBuilder(state, deps, node_id, role_key)
                prompt = builder.render_prompt(prompt_name)

            messages = [Message(role="user", content=prompt)]

            text_parts: list[str] = []
            pending_tool_names: list[str] = []

            for ev in chat_stream(
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
            ):
                if ev.type == "delta_text" and ev.text:
                    text_parts.append(ev.text)
                elif ev.type == "delta_thinking" and ev.text:
                    span.thinking(ev.text)
                elif ev.type == "tool_call" and ev.tool_call:
                    pending_tool_names.append(ev.tool_call.name)
                elif ev.type == "tool_result" and ev.text is not None:
                    tool_name = pending_tool_names.pop(0) if pending_tool_names else "unknown_tool"
                    apply_tool_result(state, tool_name, ev.text)
                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")
                elif ev.type == "done":
                    break

            obj = parse_first_json_object(" ".join(text_parts))
            stop = apply_handoff(state, obj)
            if stop:
                break

        span.end_ok()
        return state
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise