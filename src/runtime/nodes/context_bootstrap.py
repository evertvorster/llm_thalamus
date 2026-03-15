from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import (
    append_node_trace,
    get_emitter,
    run_tools_mechanically,
)

NODE_ID = "context.bootstrap"
GROUP = "context"
LABEL = "Context Bootstrap"
ROLE_KEY = ""


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _configured_chat_history_limit(resources) -> int:
    raw = getattr(resources, "prefill_chat_history_limit", 4)
    try:
        value = int(raw)
    except Exception:
        value = 4
    return max(0, value)


def _configured_memory_k(resources) -> int:
    raw = getattr(resources, "prefill_memory_k", 6)
    try:
        value = int(raw)
    except Exception:
        value = 6
    return max(0, value)


def _build_prefill_calls(*, state: State, resources) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    chat_limit = _configured_chat_history_limit(resources)
    if chat_limit > 0:
        calls.append(("chat_history_tail", {"limit": chat_limit}))

    world = state.get("world", {})
    if not isinstance(world, dict):
        world = {}

    query = _topic_query_from_world(world)
    memory_k = _configured_memory_k(resources)
    if query and memory_k > 0:
        calls.append(("openmemory_query", {"query": query, "k": memory_k}))

    return calls


def _topic_query_from_world(world: dict[str, Any]) -> str:
    topics = world.get("topics")
    if not isinstance(topics, list):
        topics = []

    parts: list[str] = []

    project = world.get("project")
    if isinstance(project, str) and project.strip():
        parts.append(project.strip())

    for topic in topics[:8]:
        if isinstance(topic, str) and topic.strip():
            parts.append(topic.strip())

    return " | ".join(parts).strip()


def _normalize_chat_turn_source(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    records = payload.get("records")
    if not isinstance(records, list):
        return None

    filtered_records: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if _is_synthetic_history_dump_message(rec):
            continue
        filtered_records.append(rec)

    return {
        "kind": "chat_turns",
        "title": "Recent chat turns",
        "records": filtered_records,
    }


def _is_synthetic_history_dump_message(record: dict[str, Any]) -> bool:
    role = str(record.get("role") or "").strip().lower()
    if role not in {"assistant", "you"}:
        return False

    content = record.get("content")
    if not isinstance(content, str):
        return False
    text = content.strip().lower()
    if len(text) < 80:
        return False

    has_turn_dump_intro = (
        ("chat turns" in text and "here are the last" in text)
        or ("most recent chat turns" in text)
    )
    has_serialized_turns = ('{"content":' in content or '"role":' in content)
    return has_turn_dump_intro and has_serialized_turns


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None


def _safe_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_candidate_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, dict):
        return []

    for key in ("memories", "results", "data", "items", "contextual", "factual", "unified"):
        maybe = value.get(key)
        if isinstance(maybe, list):
            return list(maybe)
    return [value]


def _extract_json_from_noisy_text(text: str) -> Any:
    s = text.strip()
    if not s:
        return None

    try:
        return json.loads(s)
    except Exception:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        if start < 0:
            continue

        depth = 0
        in_str = False
        esc = False

        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue

            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = s[start : i + 1].strip()
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    return None


def _candidate_text_fragments(payload: dict[str, Any]) -> list[str]:
    fragments: list[str] = []
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        fragments.append(text.strip())

    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                s = item["text"].strip()
                if s:
                    fragments.append(s)
    return fragments


def _extract_candidate_memories(payload: dict[str, Any]) -> list[Any]:
    out: list[Any] = []

    for fragment in _candidate_text_fragments(payload):
        parsed = _extract_json_from_noisy_text(fragment)
        if parsed is None:
            continue
        out.extend(_extract_candidate_items(parsed))

    raw = payload.get("raw")
    if isinstance(raw, dict):
        result = raw.get("result")
        out.extend(_extract_candidate_items(result))

    return out


def _normalize_memory_record(candidate: Any) -> dict[str, Any] | None:
    obj: dict[str, Any] | None = None
    if isinstance(candidate, dict):
        obj = candidate
    elif isinstance(candidate, str):
        s = candidate.strip()
        if not s:
            return None
        obj = {"text": s}
    else:
        return None

    text = ""
    for key in ("text", "content", "memory", "fact", "value"):
        text = _safe_text(obj.get(key))
        if text:
            break
    if not text and isinstance(obj.get("message"), dict):
        msg = obj["message"]
        if isinstance(msg, dict):
            text = _safe_text(msg.get("content"))
    if not text:
        return None

    rec_id = None
    for key in ("id", "memory_id", "uuid", "key"):
        value = obj.get(key)
        if value is None:
            continue
        s = str(value).strip()
        if s:
            rec_id = s
            break

    score = None
    for key in ("score", "salience", "relevance", "similarity"):
        score = _safe_float(obj.get(key))
        if score is not None:
            break

    sector = None
    for key in ("sector", "type", "category"):
        s = _safe_text(obj.get(key))
        if s:
            sector = s
            break

    return {
        "id": rec_id,
        "text": text,
        "score": score,
        "sector": sector,
    }


def _normalize_memory_source(payload: Any) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        seen: set[tuple[str | None, str]] = set()
        for candidate in _extract_candidate_memories(payload):
            normalized = _normalize_memory_record(candidate)
            if normalized is None:
                continue
            key = (normalized.get("id"), normalized["text"])
            if key in seen:
                continue
            seen.add(key)
            records.append(normalized)

    return {
        "kind": "memories",
        "title": "Memory candidates",
        "records": records,
    }


def _apply_context_op(
    *,
    toolset,
    ctx: dict[str, Any],
    op: dict[str, Any],
    emitter,
    node_id: str,
    span_id: str | None,
) -> dict[str, Any]:
    apply_msgs = run_tools_mechanically(
        toolset=toolset,
        calls=[("context_apply_ops", {"context": ctx, "ops": [op]})],
        emitter=emitter,
        node_id=node_id,
        span_id=span_id,
    )
    if not apply_msgs:
        raise RuntimeError("context_bootstrap: context_apply_ops unavailable")

    result = _safe_json_loads(apply_msgs[0].content or "")
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"context_bootstrap: context_apply_ops failed: {result}")

    updated = result.get("context")
    if not isinstance(updated, dict):
        raise RuntimeError("context_bootstrap: context_apply_ops returned invalid context")

    return updated


def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    def node(state: State) -> State:
        append_node_trace(state, NODE_ID)

        emitter = get_emitter(state)
        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            ctx = state.setdefault("context", {})
            if not isinstance(ctx, dict):
                ctx = {}
                state["context"] = ctx

            toolset = services.tools.toolset_for_node("context_bootstrap")

            calls = _build_prefill_calls(state=state, resources=services.tool_resources)

            tool_msgs = run_tools_mechanically(
                toolset=toolset,
                calls=calls,
                emitter=emitter,
                node_id=NODE_ID,
                span_id=getattr(span, "span_id", None),
            )

            for msg in tool_msgs:
                payload = _safe_json_loads(msg.content or "")
                if payload is None:
                    continue

                tool_name = msg.name or ""

                if tool_name == "chat_history_tail":
                    entry = _normalize_chat_turn_source(payload)
                    if entry is None:
                        continue
                    ctx = _apply_context_op(
                        toolset=toolset,
                        ctx=ctx,
                        op={"op": "upsert_source", "source": entry},
                        emitter=emitter,
                        node_id=NODE_ID,
                        span_id=getattr(span, "span_id", None),
                    )
                    state["context"] = ctx
                    continue

                if tool_name == "openmemory_query":
                    entry = _normalize_memory_source(payload)
                    if entry is None:
                        continue
                    ctx = _apply_context_op(
                        toolset=toolset,
                        ctx=ctx,
                        op={"op": "upsert_source", "source": entry},
                        emitter=emitter,
                        node_id=NODE_ID,
                        span_id=getattr(span, "span_id", None),
                    )
                    state["context"] = ctx
                    continue

            rt = state.setdefault("runtime", {})
            if not isinstance(rt, dict):
                rt = {}
                state["runtime"] = rt

            prefill_entries: list[dict[str, Any]] = []
            for (tool_name, args), msg in zip(calls, tool_msgs):
                if tool_name not in {"chat_history_tail", "openmemory_query"}:
                    continue
                prefill_entries.append(
                    {
                        "tool_name": tool_name,
                        "args": args,
                        "result": _safe_json_loads(msg.content or ""),
                    }
                )

            rt["context_bootstrap_status"] = "ok"
            rt["context_bootstrap_seeded"] = True
            rt["context_bootstrap_prefill"] = prefill_entries

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
        prompt_name=None,
    )
)
