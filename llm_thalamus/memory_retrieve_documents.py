from datetime import datetime
from typing import Any, Dict, List, Optional

from memory_retrieval import _query_memories_raw, get_default_user_id


def _parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _build_query_from_metadata(meta: Dict[str, Any]) -> str:
    if "query" in meta and meta["query"]:
        return str(meta["query"])

    pieces: List[str] = []

    filename = meta.get("filename") or meta.get("file_name")
    if filename:
        pieces.append(str(filename))

    topic = meta.get("topic")
    if topic:
        pieces.append(str(topic))

    note = meta.get("note")
    if note:
        pieces.append(str(note))

    provider = meta.get("provider")
    if provider:
        pieces.append(f"provided by {provider}")

    return " ".join(pieces) or "document relevant to current request"


def retrieve_document_from_metadata(
    meta: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    k: int = 50,
    default_tags: Optional[List[str]] = None,
    strategy: str = "latest",
    as_of: Optional[str] = None,
) -> str:
    """
    ONE-STEP document retrieval:

    - Runs a single OpenMemory query.
    - Enforces:
        - 'file_ingest' tag (so only ingested docs)
        - AND semantics on tags (file_ingest + your tags)
    - Optionally applies `as_of` cutoff on ingested_at.
    - Selects a version according to `strategy` and returns its content.
    """
    if user_id is None:
        user_id = get_default_user_id()

    # ---- required tags: always include 'file_ingest' ----
    meta_tags = meta.get("tags") or []
    base_defaults = ["file_ingest"]
    if default_tags:
        base_defaults.extend(default_tags)

    required_tags: List[str] = []
    for t in base_defaults + list(meta_tags):
        if t not in required_tags:
            required_tags.append(t)

    def tag_filter(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not required_tags:
            return results
        req = set(required_tags)
        kept = []
        for m in results:
            mem_tags = set(m.get("tags") or [])
            if req.issubset(mem_tags):
                kept.append(m)
        return kept or results

    # ---- build query (prefer filename if present) ----
    filename = meta.get("filename") or meta.get("file_name")
    if filename:
        query = filename
    else:
        query = _build_query_from_metadata(meta)

    # ---- SINGLE OpenMemory call ----
    results = _query_memories_raw(
        query,
        k=k,
        user_id=user_id,
        tags=required_tags,
    )

    # enforce AND semantics on tags locally
    candidates = tag_filter(results)
    if not candidates:
        raise ValueError(
            f"No document candidates for query={query!r} with tags={required_tags!r}"
        )

    # ---- local selection logic (no extra OpenMemory calls) ----
    def meta_of(m: Dict[str, Any]) -> Dict[str, Any]:
        return m.get("metadata") or {}

    def ingested_dt(m: Dict[str, Any]) -> Optional[datetime]:
        return _parse_iso(meta_of(m).get("ingested_at"))

    def content_len(m: Dict[str, Any]) -> int:
        text = m.get("content") or m.get("text") or ""
        return len(text)

    def score_of(m: Dict[str, Any]) -> float:
        s = m.get("score")
        return float(s) if s is not None else 0.0

    # as_of: only for 'latest' strategy
    if strategy == "latest" and as_of:
        cutoff = _parse_iso(as_of)
        if cutoff is not None:
            filtered = [m for m in candidates if (ingested_dt(m) or cutoff) <= cutoff]
            if filtered:
                candidates = filtered

    if strategy == "latest":
        chosen = max(
            candidates,
            key=lambda m: (ingested_dt(m) or datetime.min, content_len(m), score_of(m)),
        )
    elif strategy == "earliest":
        chosen = min(
            candidates,
            key=lambda m: ( ingested_dt(m) or datetime.max, ),
        )
    elif strategy == "longest":
        chosen = max(
            candidates,
            key=lambda m: (content_len(m), score_of(m)),
        )
    elif strategy == "score":
        chosen = max(candidates, key=lambda m: score_of(m))
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}")

    content = chosen.get("content") or chosen.get("text")
    if not content:
        raise ValueError("Selected document has no content/text field.")

    return content
