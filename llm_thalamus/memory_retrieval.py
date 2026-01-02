"""
Read-side helper module for llm-thalamus.

This module encapsulates:
- Loading config/config.json
- Constructing an OpenMemory client
- High-level helper functions to query memories

Project policy (single-user + reduced tag semantics):
- user_id is ignored (single-user system).
- tags are ignored for querying (we do not do tag-based filtering).
- EXCEPTION: Sector-block retrieval only includes memories that have at least one tag.
  (We do not care what the tag is — the presence of any tag is the gate.)

Memory annotation display policy:
- Whether Tag / Metadata lines are rendered in memory blocks is controlled by config:
  thalamus.calls.answer.flags.show_memory_annotations (boolean, default false).

Public API (for the controller / LLM):
- query_memories(...)       -> str  (LLM-ready text)
- query_semantic(...)       -> str
- query_episodic(...)       -> str
- query_procedural(...)     -> str

Internal/raw helper (if we ever need structured data later):
- _query_memories_raw(...)  -> List[Dict[str, Any]]
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import re

from paths import get_user_config_path, resolve_app_path

if TYPE_CHECKING:
    from openmemory import Memory



def _strip_query_lines(block: str) -> str:
    """Remove 'Query: ...' lines from formatted memory blocks (cosmetic)."""
    if not isinstance(block, str) or not block:
        return block
    return re.sub(r"^Query:.*\n", "", block, flags=re.MULTILINE)


# Path to the shared config file
_CONFIG_PATH = get_user_config_path()

_MEM: Optional[Memory] = None
_CFG: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load and cache the config from config/config.json."""
    global _CFG
    if _CFG is None:
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            _CFG = json.load(f)
    return _CFG


def _show_memory_annotations() -> bool:
    """
    Whether memory annotations (Tag / Metadata) should be rendered
    in formatted memory blocks.

    Controlled by config:
      thalamus.calls.answer.flags.show_memory_annotations

    Defaults to False if the config key is missing or unreadable.
    """
    cfg = _load_config()
    try:
        return bool(
            cfg["thalamus"]["calls"]["answer"]["flags"].get(
                "show_memory_annotations", False
            )
        )
    except Exception:
        return False


def run_om_async(coro):
    """
    Run an OpenMemory coroutine from synchronous llm-thalamus code.

    Notes:
    - llm-thalamus is primarily synchronous; openmemory-py 1.3.x exposes an async API.
    - If an asyncio loop is already running in this thread, we fail fast with a clear error
      instead of deadlocking or attempting unsafe nesting.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        raise RuntimeError(
            "run_om_async() was called while an asyncio event loop is already running in "
            "this thread. Call the OpenMemory methods with 'await' from async code, or "
            "move OpenMemory calls to a non-async thread/worker boundary."
        )

    return asyncio.run(coro)


def _maybe_set_env(key: str, value: Optional[str]) -> None:
    """Set an env var if value is a non-empty string."""
    if value is None:
        return
    if isinstance(value, str) and value.strip():
        os.environ[key] = value.strip()


def _build_memory_client(cfg: Dict[str, Any]) -> "Memory":
    """
    Construct an OpenMemory Memory() client.

    openmemory-py 1.3.1 removed openmemory.OpenMemory and replaced it with
    openmemory.Memory(user=None) and async methods (add/search/history/get/delete/delete_all/source).

    llm-thalamus remains synchronous; async OpenMemory calls are executed via run_om_async().

    IMPORTANT:
    - We rely on OpenMemory's own sectoring (primary_sector), which only behaves as expected
      when OM_TIER is configured appropriately (e.g., 'deep').
    - We do NOT rely on openmemory-py's search(filters=...) for sector retrieval; instead,
      we bucket results client-side by the returned 'primary_sector' field.
    """
    # Keep existing config validation for embeddings provider so misconfiguration
    # remains obvious, even though Memory() is now top-level.
    emb_cfg = cfg.get("embeddings", {})
    provider = emb_cfg.get("provider", "ollama")
    if provider != "ollama":
        raise NotImplementedError(
            f"Only 'ollama' embeddings are implemented in this project, got: {provider!r}"
        )

    # Propagate key OpenMemory env configuration from config if present.
    # This avoids "silent defaults" drifting the runtime behavior.
    om_cfg = cfg.get("openmemory", {}) or {}
    raw_path = om_cfg.get("path")
    if isinstance(raw_path, str) and raw_path.strip():
        resolved = resolve_app_path(raw_path.strip(), kind="data")
        _maybe_set_env("OM_DB_PATH", str(resolved))
    _maybe_set_env("OM_TIER", om_cfg.get("tier"))

    # If your config carries an Ollama embedding model name, pass it through.
    # (OpenMemory reads OM_OLLAMA_MODEL when using the Ollama adapter.)
    _maybe_set_env("OM_OLLAMA_MODEL", emb_cfg.get("model") or om_cfg.get("ollama_model"))

    return Memory(user=None)


def get_memory() -> "Memory":
    """Return a shared Memory() instance suitable for retrieval operations."""
    global _MEM
    if _MEM is None:
        cfg = _load_config()
        _MEM = _build_memory_client(cfg)
    return _MEM


def get_default_user_id() -> str:
    """
    Legacy helper retained for compatibility with older call sites.

    This project is single-user, so user_id scoping is intentionally ignored.
    """
    return "default"


# ---------------------------------------------------------------------------
# RAW retrieval helper (returns structured objects)
# ---------------------------------------------------------------------------

async def _search_async(
    mem: "Memory",
    query: str,
    *,
    k: int,
) -> Any:
    """
    Compatibility shim for openmemory-py search() argument names across minor versions.

    We attempt several common keyword variants and fall back on a clear TypeError
    if none match.
    """
    variants: List[Dict[str, Any]] = []

    # Most likely shapes
    variants.append({"query": query, "k": k})
    variants.append({"query": query, "n": k})
    variants.append({"query": query, "limit": k})

    last_err: Optional[BaseException] = None
    for kwargs in variants:
        kwargs = {kk: vv for kk, vv in kwargs.items() if vv is not None}
        try:
            return await mem.search(**kwargs)
        except TypeError as e:
            last_err = e
            continue

    raise TypeError(
        f"OpenMemory Memory.search() did not accept any of the attempted argument "
        f"signatures; last error: {last_err}"
    ) from last_err


def _get_primary_sector(item: Dict[str, Any]) -> Optional[str]:
    """Return the normalized primary sector for an item, if present."""
    ps = item.get("primary_sector")
    if ps is None:
        ps = item.get("primarySector")
    if ps is None and isinstance(item.get("sector"), str):
        ps = item.get("sector")
    if isinstance(ps, str):
        ps = ps.strip().lower()
        return ps if ps else None
    return None


def _filter_by_sectors(
    results: List[Dict[str, Any]],
    sectors: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """Client-side sector filtering using OpenMemory's 'primary_sector' output."""
    if not sectors:
        return results

    want = {str(s).strip().lower() for s in sectors if isinstance(s, str) and s.strip()}
    if not want:
        return results

    out: List[Dict[str, Any]] = []
    for item in results:
        ps = _get_primary_sector(item)
        if ps in want:
            out.append(item)
    return out


def _query_memories_raw(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,          # legacy / ignored
    sectors: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,        # legacy / ignored
) -> List[Dict[str, Any]]:
    """
    Low-level helper: run a semantic memory query and return raw results.

    Notes:
    - Single-user system: we do NOT filter by user_id.
    - We do NOT rely on tag filtering in OpenMemory.
    - We do NOT rely on search(filters=...) for sector retrieval (unreliable in 1.3.1);
      we filter by sectors client-side using each item's 'primary_sector' field.
    """
    mem = get_memory()

    # Fetch a candidate set, then filter client-side if sectors were requested.
    results = run_om_async(_search_async(mem, query, k=k))
    results_list = list(results)

    return _filter_by_sectors(results_list, sectors)


def query_memories_raw(
    query: str,
    *,
    k: int = 10,
    sectors: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Public wrapper: run a semantic memory query and return raw structured results.

    Intended for deterministic post-processing in thalamus (e.g., rule validation
    and consolidation) without having to parse formatted text blocks.

    Notes:
    - Single-user system: user_id is ignored.
    - We do NOT rely on tag filtering in OpenMemory (tags are not supported for querying).
    - Sector filtering is performed client-side on 'primary_sector'.
    """
    return _query_memories_raw(
        query,
        k=k,
        sectors=sectors,
    )


# ---------------------------------------------------------------------------
# Formatting helpers (LLM-ready text)
# ---------------------------------------------------------------------------

def _format_memory_entry(
    m: Dict[str, Any],
    idx: int,
) -> str:
    """
    Format a single memory entry for human/LLM-readable text.

    IMPORTANT:
    - We do not attempt to JSON-decode or transform content.
    - Whatever was stored in OpenMemory as the content string comes out as-is.

    Annotation rendering:
    - Tag/Metadata lines are only included when enabled via config:
      thalamus.calls.answer.flags.show_memory_annotations
    """
    content = m.get("content") or m.get("text") or ""
    primary_sector = m.get("primary_sector")
    if primary_sector is None:
        primary_sector = m.get("primarySector")
    sectors = m.get("sectors")
    metadata = m.get("meta") if m.get("meta") is not None else m.get("metadata")
    score = m.get("score")

    lines: List[str] = []
    lines.append(f"[{idx}]")
    if score is not None:
        try:
            lines.append(f"Score: {score:.4f}")
        except Exception:
            lines.append(f"Score: {score}")
    if primary_sector is not None:
        lines.append(f"PrimarySector: {primary_sector}")
    if sectors is not None:
        lines.append(f"Sectors: {sectors}")

    if _show_memory_annotations():
        tags_val = m.get("tags") or []
        if isinstance(tags_val, list) and tags_val:
            lines.append(f"Tag: {tags_val[0]}")
        elif isinstance(tags_val, str) and tags_val:
            lines.append(f"Tag: {tags_val}")

        if metadata is not None:
            lines.append(f"Metadata: {metadata}")

    if content:
        lines.append(f"Content: {content}")
    return "\n".join(lines)


def _format_memories_block(
    label: str,
    query: str,
    results: List[Dict[str, Any]],
) -> str:
    """Build a single LLM-ready text block for a set of memories."""
    lines: List[str] = []
    lines.append(f"### {label}")
    lines.append(f"Query: {query}")
    lines.append(f"Results: {len(results)}")
    if not results:
        lines.append("No memories found.")
        return "\n".join(lines)

    for i, m in enumerate(results, start=1):
        lines.append("")
        lines.append(_format_memory_entry(m, i))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sector-based retrieval helpers
# ---------------------------------------------------------------------------

ALLOWED_MEMORY_SECTORS: List[str] = [
    "reflective",
    "semantic",
    "procedural",
    "episodic",
    "emotional",
]


def _format_sector_block_label(sector: str) -> str:
    return f"{sector.capitalize()} Memories"


def _require_any_tag(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sector-block rule: only include memories that have at least one tag.

    We do not care what the tag is; this simply prevents untagged items
    from entering the sectored memory blocks.
    """
    out: List[Dict[str, Any]] = []
    for item in results:
        tags_val = item.get("tags") or []
        if tags_val:
            out.append(item)
    return out


def query_memories_by_sector_blocks(
    query: str,
    *,
    limits_by_sector: Dict[str, int],
    candidate_multiplier: int = 4,
    include_sectors: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Return an LLM-ready memory block per OpenMemory sector.

    Implementation notes:
    - openmemory-py 1.3.1 does not reliably support sector filtering via search(filters=...).
    - We therefore retrieve a single candidate set and bucket by each item's 'primary_sector'.
    - OpenMemory is still the source of truth for sector assignment (OM_TIER=deep recommended).

    Policy:
    - Sector-block retrieval only includes memories that have at least one tag (any tag).
    """
    sectors_to_use = include_sectors or ALLOWED_MEMORY_SECTORS
    blocks: Dict[str, str] = {}

    # Determine how many candidates to retrieve once.
    mult = int(candidate_multiplier) if candidate_multiplier and candidate_multiplier > 0 else 1
    max_k = 0
    for sector in sectors_to_use:
        k = int(limits_by_sector.get(sector, 0) or 0)
        if k > max_k:
            max_k = k
    if max_k <= 0:
        return {s: "" for s in sectors_to_use}

    candidate_k = max_k * mult

    # One retrieval, then bucket by primary_sector.
    raw_all = _query_memories_raw(query, k=candidate_k)
    raw_all = _require_any_tag(raw_all)

    buckets: Dict[str, List[Dict[str, Any]]] = {s: [] for s in sectors_to_use}
    for item in raw_all:
        ps = _get_primary_sector(item)
        if ps in buckets:
            buckets[ps].append(item)

    for sector in sectors_to_use:
        k = int(limits_by_sector.get(sector, 0) or 0)
        if k <= 0:
            blocks[sector] = ""
            continue

        raw = buckets.get(sector, [])[:k]
        blocks[sector] = _format_memories_block(
            _format_sector_block_label(sector),
            query,
            raw,
        )

    for _k, _v in list(blocks.items()):
        if isinstance(_v, str) and _v:
            blocks[_k] = _strip_query_lines(_v)

    return blocks


# ---------------------------------------------------------------------------
# Public API: retrieval functions that return TEXT
# ---------------------------------------------------------------------------

def query_memories(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,           # legacy / ignored
    sectors: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,        # legacy / ignored
    label: str = "Memories",
) -> str:
    """
    High-level retrieval function for llm-thalamus.

    Single-user system:
    - user_id is ignored
    - tags are ignored

    Sector filtering:
    - performed client-side by 'primary_sector' (OpenMemory is the source of truth)

    Annotation rendering is config-driven:
      thalamus.calls.answer.flags.show_memory_annotations
    """
    raw = _query_memories_raw(
        query,
        k=k,
        user_id=user_id,
        sectors=sectors,
        tags=tags,
    )
    return _strip_query_lines(_format_memories_block(label, query, raw))


def query_semantic(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,           # legacy / ignored
    tags: Optional[List[str]] = None,        # legacy / ignored
) -> str:
    """Retrieve semantic-style memories and return them as an LLM-ready text block."""
    return query_memories(
        query,
        k=k,
        user_id=user_id,
        sectors=["semantic"],
        tags=tags,
        label="Semantic Memories",
    )


def query_episodic(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,           # legacy / ignored
    tags: Optional[List[str]] = None,        # legacy / ignored
) -> str:
    """Retrieve episodic-style memories and return them as an LLM-ready text block."""
    return query_memories(
        query,
        k=k,
        user_id=user_id,
        sectors=["episodic"],
        tags=tags,
        label="Episodic Memories",
    )


def query_procedural(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,           # legacy / ignored
    tags: Optional[List[str]] = None,        # legacy / ignored
) -> str:
    """Retrieve procedural-style memories and return them as an LLM-ready text block."""
    return query_memories(
        query,
        k=k,
        user_id=user_id,
        sectors=["procedural"],
        tags=tags,
        label="Procedural Memories",
    )


def print_memories(label: str, query: str, text_block: str) -> None:
    """CLI helper for debugging."""
    print(f"\n=== {label} ===")
    print(text_block)
