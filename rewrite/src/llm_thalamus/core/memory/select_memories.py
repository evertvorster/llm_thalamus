from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm_thalamus.adapters.openmemory.client import get_default_user_id, search


def _normalize_text(s: Any) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return s.replace("\r\n", "\n").strip()


def _truncate(s: str, limit: int) -> str:
    if limit <= 0:
        return s
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


def _coerce_result_to_dict(r: Any) -> Optional[Dict[str, Any]]:
    if isinstance(r, dict):
        return r
    return None


def query_memories_raw(
    query: str,
    *,
    k: int = 8,
    sector: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Raw memory search results as list of dicts.
    Optional client-side filter by primary_sector.
    """
    uid = user_id or get_default_user_id()
    results = search(query=query, k=int(k), user_id=uid)

    out: List[Dict[str, Any]] = []
    for r in results:
        d = _coerce_result_to_dict(r)
        if not d:
            continue
        if sector:
            ps = str(d.get("primary_sector", "") or "").lower()
            if ps != sector.lower():
                continue
        out.append(d)
    return out


def query_memories_by_sector(
    query: str,
    *,
    k: int = 12,
    user_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group memories by primary_sector.
    """
    uid = user_id or get_default_user_id()
    results = search(query=query, k=int(k), user_id=uid)

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        d = _coerce_result_to_dict(r)
        if not d:
            continue
        sector = str(d.get("primary_sector", "") or "unknown").lower()
        buckets.setdefault(sector, []).append(d)
    return buckets


def format_memories_block(
    results: List[Dict[str, Any]],
    *,
    max_items: int = 8,
    max_chars_per_item: int = 800,
) -> str:
    """
    Convert raw results into the LLM-facing 'memories block' format.
    Kept for compatibility; caller can bypass later.
    """
    if not results:
        return ""

    lines: List[str] = []
    for i, r in enumerate(results[:max_items], start=1):
        content = _normalize_text(r.get("content", ""))
        if not content:
            continue

        sector = _normalize_text(r.get("primary_sector", ""))
        score = r.get("score", None)
        meta = r.get("metadata", None)

        content = _truncate(content, max_chars_per_item)

        header = f"{i}."
        if sector:
            header += f" [{sector}]"
        if score is not None:
            header += f" score={score}"
        if meta and isinstance(meta, dict):
            # keep it compact
            ctype = meta.get("content_type")
            if ctype:
                header += f" type={ctype}"

        lines.append(f"{header}\n{content}")

    return "\n\n".join(lines).strip()


def query_memories_block(
    query: str,
    *,
    k: int = 8,
    sector: Optional[str] = None,
    user_id: Optional[str] = None,
    max_items: int = 8,
    max_chars_per_item: int = 800,
) -> str:
    results = query_memories_raw(query, k=k, sector=sector, user_id=user_id)
    return format_memories_block(
        results,
        max_items=max_items,
        max_chars_per_item=max_chars_per_item,
    )
