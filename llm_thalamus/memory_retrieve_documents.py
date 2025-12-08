from datetime import datetime
from typing import Any, Dict, List, Optional

from memory_retrieval import _query_memories_raw, get_default_user_id, get_memory


def _parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def _build_query_from_metadata(meta: Dict[str, Any]) -> str:
    """
    Build a reasonable query string from the metadata if no explicit 'query'
    is supplied. Prefer filename/topic/note/provider in that order.
    """
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


def _get_memory_by_id(memory_id: str, user_id: str) -> Dict[str, Any]:
    """
    Retrieve a single memory by its OpenMemory ID using the Python SDK.

    The current Python API exposes:
        - add(...)
        - query(...)
        - getAll(...)
        - getBySector(...)
        - delete(...)

    There is no direct `get(id)` helper, so we scan `getAll` for now.
    This is acceptable at current scales and keeps everything inside
    OpenMemory (no disk fallback).
    """
    mem = get_memory()

    # For now we assume a modest memory size; adjust limit if needed.
    # If the DB gets huge later, we can revisit this.
    all_mems = mem.getAll(limit=10000, offset=0)

    target = str(memory_id)
    for m in all_mems:
        mid = str(m.get("id") or m.get("memoryId") or "")
        if mid == target:
            # Found exact ID match
            return m

    raise ValueError(f"No document found in OpenMemory for id={memory_id!r}")


def retrieve_document_from_metadata(
    meta: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    k: int = 50,
    default_tags: Optional[List[str]] = None,
    strategy: str = "latest",
    as_of: Optional[str] = None,
    target_id: Optional[str] = None,
) -> str:
    """
    ONE-STEP document retrieval.

    Behaviour:
    ----------
    1. If `target_id` is provided:
       - Fetch that memory directly from OpenMemory (via getAll + ID match).
       - Validate that it is a file_ingest memory.
       - Return its content/text.

    2. Otherwise:
       - Build a query string from `meta` (prefer filename).
       - Enforce strict AND semantics on tags:
           - Always include 'file_ingest'
           - Plus any `default_tags`
           - Plus any `meta['tags']`
       - Call `_query_memories_raw(...)` once.
       - Filter to memories where all required tags are present.
       - Optionally apply `as_of` cutoff for 'latest'.
       - Select a version according to `strategy`:
           - 'latest', 'earliest', 'longest', 'score'
       - Return the selected memory's content.

    Returns a single document string.
    """
    # ------------------------------------------------------------------
    # Resolve user_id
    # ------------------------------------------------------------------
    if user_id is None:
        user_id = get_default_user_id()

    # ------------------------------------------------------------------
    # 0. Hard override: retrieve by explicit OpenMemory ID
    # ------------------------------------------------------------------
    if target_id:
        mem = _get_memory_by_id(str(target_id), user_id=user_id)
        tags = mem.get("tags") or []

        # We expect file_ingest memories for document ingestion; in this setup,
        # 'file_ingest' is conveyed via tags rather than metadata['kind'].
        if "file_ingest" not in tags:
            raise ValueError(
                f"Memory {target_id!r} does not have the 'file_ingest' tag; "
                f"tags={tags}"
            )

        content = mem.get("content") or mem.get("text")
        if not content:
            raise ValueError(
                f"Memory {target_id!r} has no content/text field; "
                f"keys={list(mem.keys())}"
            )
        return content

    # ------------------------------------------------------------------
    # 1. Build required tags (strict AND semantics)
    # ------------------------------------------------------------------
    meta_tags = meta.get("tags") or []
    base_defaults = ["file_ingest"]
    if default_tags:
        base_defaults.extend(default_tags)

    required_tags: List[str] = []
    for t in base_defaults + list(meta_tags):
        if t not in required_tags:
            required_tags.append(t)

    def tag_filter(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enforce strict AND semantics on tags.

        Only keep memories where ALL required_tags are present.
        No fallback to untagged memories; if nothing matches, we fail.
        """
        if not required_tags:
            return results
        req = set(required_tags)
        kept: List[Dict[str, Any]] = []
        for m in results:
            mem_tags = set(m.get("tags") or [])
            if req.issubset(mem_tags):
                kept.append(m)
        return kept

    # ------------------------------------------------------------------
    # 2. Build query (prefer filename)
    # ------------------------------------------------------------------
    filename = meta.get("filename") or meta.get("file_name")
    if filename:
        query = str(filename)
    else:
        query = _build_query_from_metadata(meta)

    # ------------------------------------------------------------------
    # 3. Single OpenMemory call (semantic search)
    # ------------------------------------------------------------------
    results = _query_memories_raw(
        query,
        k=k,
        user_id=user_id,
        tags=required_tags,
    )

    # Enforce AND semantics on tags locally
    candidates = tag_filter(results)

    if not candidates:
        raise ValueError(
            f"No document candidates for query={query!r} with required "
            f"tags={required_tags!r}"
        )

    # ------------------------------------------------------------------
    # 4. Local selection logic (temporal/version strategies)
    # ------------------------------------------------------------------
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
            key=lambda m: (
                ingested_dt(m) or datetime.min,
                content_len(m),
                score_of(m),
            ),
        )
    elif strategy == "earliest":
        chosen = min(
            candidates,
            key=lambda m: (ingested_dt(m) or datetime.max,),
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
