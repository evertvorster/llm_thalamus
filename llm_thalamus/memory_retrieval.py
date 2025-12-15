"""
memory_retrieval.py

Read-side helper module for llm-thalamus.

This module encapsulates:
- Loading config/config.json
- Constructing an OpenMemory client (local SQLite + Ollama embeddings)
- High-level helper functions to query memories

Project policy (single-user + reduced tag semantics):
- user_id is ignored (single-user system).
- tags are ignored for querying (we do not do tag-based filtering).
- EXCEPTION: Sector-block retrieval only includes memories that have at least one tag.
  (We do not care what the tag is — the presence of any tag is the gate.)

Public API (for the controller / LLM):
- query_memories(...)       -> str  (LLM-ready text)
- query_semantic(...)       -> str
- query_episodic(...)       -> str
- query_procedural(...)     -> str

Internal/raw helper (if we ever need structured data later):
- _query_memories_raw(...)  -> List[Dict[str, Any]]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from openmemory import OpenMemory


def _strip_query_lines(block: str) -> str:
    """Remove 'Query: ...' lines from formatted memory blocks (cosmetic)."""
    if not isinstance(block, str) or not block:
        return block
    return re.sub(r"^Query:.*\n", "", block, flags=re.MULTILINE)


# Path to the shared config file
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.json"

_MEM: Optional[OpenMemory] = None
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
    """
    cfg = _load_config()
    try:
        return bool(
            cfg["thalamus"]["calls"]["answer"]["flags"]
               .get("show_memory_annotations", False)
        )
    except Exception:
        return False


def _build_memory_client(cfg: Dict[str, Any]) -> OpenMemory:
    """Construct an OpenMemory client from the given config dict."""
    om_cfg = cfg["openmemory"]
    emb_cfg = cfg["embeddings"]

    provider = emb_cfg["provider"]
    if provider != "ollama":
        raise NotImplementedError(
            f"Only 'ollama' embeddings are implemented in this project, got: {provider!r}"
        )

    embeddings = {
        "provider": "ollama",
        "ollama": {
            "url": emb_cfg.get("ollama_url", "http://localhost:11434"),
        },
        "model": emb_cfg["model"],
    }

    return OpenMemory(
        path=om_cfg["path"],
        tier=om_cfg.get("tier", "smart"),
        embeddings=embeddings,
    )


def get_memory() -> OpenMemory:
    """Return a shared OpenMemory instance suitable for retrieval operations."""
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
    """
    mem = get_memory()

    filters: Dict[str, Any] = {}
    if sectors:
        filters["sectors"] = sectors

    results = mem.query(query, k=k, filters=filters)
    return list(results)


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

    include_annotations:
    - When False (default), do not include Tag/Metadata lines (keeps the prompt lean).
    - When True, include Tag and Metadata if present.
    """
    content = m.get("content") or m.get("text") or ""
    primary_sector = m.get("primarySector")
    sectors = m.get("sectors")
    metadata = m.get("metadata")
    score = m.get("score")

    lines: List[str] = []
    lines.append(f"[{idx}]")
    if score is not None:
        lines.append(f"Score: {score:.4f}")
    if primary_sector is not None:
        lines.append(f"PrimarySector: {primary_sector}")
    if sectors is not None:
        lines.append(f"Sectors: {sectors}")

    if _show_memory_annotations():
        # OpenMemory typically returns tags as a list; your project uses exactly one tag.
        tags = m.get("tags") or []
        if isinstance(tags, list) and tags:
            lines.append(f"Tag: {tags[0]}")
        elif isinstance(tags, str) and tags:
            lines.append(f"Tag: {tags}")

        if metadata:
            lines.append(f"Metadata: {metadata}")

    if content:
        lines.append(f"Content: {content}")
    return "\n".join(lines)


def _format_memories_block(
    label: str,
    query: str,
    results: List[Dict[str, Any]],
    *,
    include_annotations: bool = False,
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
        lines.append(_format_memory_entry(m, i, include_annotations=include_annotations))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sector-based retrieval helpers (OpenMemory filtering supported via 'sectors')
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
        tags = item.get("tags") or []
        if tags:
            out.append(item)
    return out


def query_memories_by_sector_blocks(
    query: str,
    *,
    limits_by_sector: Dict[str, int],
    candidate_multiplier: int = 2,
    include_sectors: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Return an LLM-ready memory block per OpenMemory sector.

    - Fetches (k * candidate_multiplier) candidates per sector.
    - Filters to ONLY items that have at least one tag (any tag).
    - Returns up to k remaining items per sector.
    """
    sectors_to_use = include_sectors or ALLOWED_MEMORY_SECTORS
    blocks: Dict[str, str] = {}

    mult = int(candidate_multiplier) if candidate_multiplier and candidate_multiplier > 0 else 1

    for sector in sectors_to_use:
        k = int(limits_by_sector.get(sector, 0) or 0)
        if k <= 0:
            blocks[sector] = ""
            continue

        candidate_k = max(k, k * mult)

        raw = _query_memories_raw(
            query,
            k=candidate_k,
            sectors=[sector],
        )
        raw = _require_any_tag(raw)
        raw = raw[:k]

        blocks[sector] = _format_memories_block(
            _format_sector_block_label(sector),
            query,
            raw,
            include_annotations=False,  # keep sector blocks lean unless you decide otherwise later
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
    include_annotations: bool = False,
) -> str:
    """
    High-level retrieval function for llm-thalamus.

    Single-user system:
    - user_id is ignored
    - tags are ignored

    include_annotations:
    - When True, include Tag/Metadata lines (if present) per memory entry.
    """
    raw = _query_memories_raw(
        query,
        k=k,
        user_id=user_id,
        sectors=sectors,
        tags=tags,
    )
    return _strip_query_lines(
        _format_memories_block(label, query, raw, include_annotations=include_annotations)
    )


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
