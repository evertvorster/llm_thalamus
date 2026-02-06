from __future__ import annotations

from typing import Any, Dict, List

from orchestrator.deps import Deps
from orchestrator.state import State


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _as_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _extract_text(item: Dict[str, Any]) -> str:
    for k in ("text", "content", "memory", "value"):
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


def run_retrieval_node(state: State, deps: Deps) -> State:
    """
    Retrieval MVP:
      - deterministic, read-only
      - query = state.task.user_input
      - k = caller-specified state.task.retrieval_k OR cfg default, clamped to cfg max
      - output normalized hits to state.context.memories

    NOTE:
      Timestamp normalization is handled at the OpenMemory boundary (OpenMemoryFacade).
      Here we simply pass through the already-normalized `ts` field into context.
    """
    task = state["task"]
    ctx = state["context"]

    query = task["user_input"].strip()
    if not query:
        ctx["memories"] = []
        return state

    k_req = task.get("retrieval_k")
    if isinstance(k_req, int):
        k = k_req
    else:
        k = int(deps.cfg.orchestrator_retrieval_default_k)

    k = _clamp(k, 0, int(deps.cfg.orchestrator_retrieval_max_k))
    if k == 0:
        ctx["memories"] = []
        return state

    # IMPORTANT:
    # user_id is bound inside deps.openmemory — never referenced here
    raw = deps.openmemory.search(query, k=k)

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
                # ISO 8601 timestamp (normalized by OpenMemoryFacade from metadata.ingested_at)
                "ts": item.get("ts"),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            }
        )

    ctx["memories"] = memories
    return state
