from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.state import State


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _as_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _extract_text(item: Dict[str, Any]) -> str:
    for k in ("text", "content", "Content", "memory", "value"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    content = item.get("Content") or item.get("content")
    if isinstance(content, dict):
        for k in ("text", "content", "value"):
            v = content.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return ""


def _extract_score(item: Dict[str, Any]):
    for k in ("score", "Score", "similarity"):
        if k in item:
            return _as_float(item.get(k))
    return None


def _extract_sector(item: Dict[str, Any]) -> str:
    for k in ("PrimarySector", "sector", "type"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return "unknown"


def _collect_llm_text(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None] | None = None,
) -> str:
    """
    Collect streamed LLM response into a single string.

    UI contract (when emit is provided):
      - forward every streamed chunk as Event(type="log")
    """
    parts: list[str] = []
    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue
        if emit is not None:
            emit({"type": "log", "text": text})
        if kind == "response":
            parts.append(text)
    return "".join(parts)


def run_retrieval_node(
    state: State,
    deps: Deps,
    *,
    emit: Callable[[Event], None] | None = None,
) -> State:
    """
    Memory retrieval (router-planned):
      - LLM-enabled query generation (model: deps.models["memory_retrieval"])
      - query prompt input includes: user_input, chat_history_text (optional), world (summary/full)
      - k = state.task.retrieval_k (clamped to cfg max; 0 disables retrieval)
      - output normalized hits to state.context.memories

    NOTE:
      - This node does NOT use state.task.memory_query (router may set it, but we ignore it).
      - Keep behavior after query generation unchanged.
    """
    task = state["task"]
    ctx = state["context"]

    k_req = task.get("retrieval_k")

    k: int | None = None
    if isinstance(k_req, bool):
        k = None
    elif isinstance(k_req, int):
        k = k_req
    elif isinstance(k_req, float) and k_req.is_integer():
        k = int(k_req)
    elif isinstance(k_req, str):
        s = k_req.strip()
        if s and s.lstrip("+-").isdigit():
            k = int(s)

    if k is None:
        k = int(deps.cfg.orchestrator_retrieval_default_k)

    k = _clamp(k, 0, int(deps.cfg.orchestrator_retrieval_max_k))
    if k == 0:
        ctx["memories"] = []
        return state

    user_input = task.get("user_input") or ""
    chat_history_text = (ctx.get("chat_history_text") or "")
    world_view = (task.get("world_view") or "")
    world = state.get("world") or {}

    model = deps.models["memory_retrieval"]
    prompt = deps.prompt_loader.render(
        "memory_retrieval",
        user_input=user_input,
        chat_history_text=chat_history_text,
        world_view=world_view,
        world=world,
        intent=task.get("intent") or "",
        constraints=task.get("constraints") or [],
    )

    # CHANGED: stream query-generation tokens to UI when emit is provided
    raw_query = _collect_llm_text(deps, model=model, prompt=prompt, emit=emit)
    ctx["memory_retrieval"] = raw_query

    if not raw_query:
        raw_query = user_input

    if not raw_query:
        ctx["memories"] = []
        return state

    raw = deps.openmemory.search(raw_query, k=k)
    min_score = float(deps.cfg.orchestrator_retrieval_min_score)

    memories: List[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue

        score = _extract_score(item)
        if score is not None and score < min_score:
            continue

        text = _extract_text(item)
        if not text:
            continue

        memories.append(
            {
                "id": item.get("id") or item.get("_id"),
                "score": score,
                "sector": _extract_sector(item),
                "text": text,
                "ts": item.get("ts"),
                "metadata": item.get("metadata")
                if isinstance(item.get("metadata"), dict)
                else None,
            }
        )

    ctx["memories"] = memories
    state["runtime"]["node_trace"].append("memory_retrieval:openmemory")
    return state
