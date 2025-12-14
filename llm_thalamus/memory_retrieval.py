"""
memory_retrieval.py

Read-side helper module for llm-thalamus.

This module encapsulates:
- Loading config/config.json
- Constructing an OpenMemory client (local SQLite + Ollama embeddings)
- High-level helper functions to query memories

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
from typing import Any, Dict, List, Optional

from openmemory import OpenMemory
from paths import get_user_config_path, resolve_app_path

# Path to the shared config file (dev vs installed handled by paths.py)
_CONFIG_PATH = get_user_config_path()

_MEM: Optional[OpenMemory] = None
_CFG: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load and cache the config from config/config.json."""
    global _CFG
    if _CFG is None:
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            _CFG = json.load(f)
    return _CFG


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

    # IMPORTANT:
    # Resolve OpenMemory DB path deterministically:
    # - Absolute paths stay absolute
    # - Relative paths are anchored to the app XDG data root (NOT process CWD)
    om_path = resolve_app_path(str(om_cfg["path"]), kind="data")
    om_path.parent.mkdir(parents=True, exist_ok=True)

    return OpenMemory(
        path=str(om_path),
        tier=om_cfg.get("tier", "smart"),
        embeddings=embeddings,
    )


def get_memory() -> OpenMemory:
    """
    Return a shared OpenMemory instance suitable for retrieval operations.
    """
    global _MEM
    if _MEM is None:
        cfg = _load_config()
        _MEM = _build_memory_client(cfg)
    return _MEM


def get_default_user_id() -> str:
    """Return the default user_id from config (for single-user setups)."""
    cfg = _load_config()
    return cfg.get("thalamus", {}).get("default_user_id", "default")


# ---------------------------------------------------------------------------
# RAW retrieval helper (returns structured objects)
# ---------------------------------------------------------------------------

def _query_memories_raw(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
    sectors: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Low-level helper: run a semantic memory query and return raw results.

    This is the "truth" layer that talks directly to OpenMemory.
    All public helpers that return text are built on top of this.
    """
    mem = get_memory()
    if user_id is None:
        user_id = get_default_user_id()

    filters: Dict[str, Any] = {"user_id": user_id}
    if sectors:
        filters["sectors"] = sectors
    if tags:
        filters["tags"] = tags

    results = mem.query(query, k=k, filters=filters)
    # Ensure we return a concrete list, not a generator.
    return list(results)


# ---------------------------------------------------------------------------
# Formatting helpers (LLM-ready text)
# ---------------------------------------------------------------------------

def _format_memory_entry(m: Dict[str, Any], idx: int) -> str:
    """
    Format a single memory entry for human/LLM-readable text.

    IMPORTANT:
    - We do not attempt to JSON-decode or transform content.
    - Whatever was stored in OpenMemory as the content string comes out as-is.
    """
    content = m.get("content") or m.get("text") or ""
    primary_sector = m.get("primarySector")
    sectors = m.get("sectors")
    tags = m.get("tags")
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
    if tags:
        lines.append(f"Tags: {tags}")
    if metadata:
        lines.append(f"Metadata: {metadata}")
    if content:
        lines.append(f"Content: {content}")
    return "\n".join(lines)


def _format_memories_block(
    label: str,
    query: str,
    results: List[Dict[str, Any]],
) -> str:
    """
    Build a single LLM-ready text block for a set of memories.
    """
    lines: List[str] = []
    lines.append(f"### {label}")
    lines.append(f"Query: {query}")
    lines.append(f"Results: {len(results)}")
    if not results:
        lines.append("No memories found.")
        return "\n".join(lines)

    for i, m in enumerate(results, start=1):
        lines.append("")  # blank line between entries
        lines.append(_format_memory_entry(m, i))

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Tag-based retrieval helpers (application-level memory groupings)
# ---------------------------------------------------------------------------

# These are the application-level tags llm-thalamus uses to structure "internal memory"
# sections in the answer prompt template.
ALLOWED_MEMORY_TAGS: List[str] = [
    "reflection",
    "rule",
    "preference",
    "name",
    "fact",
    "decision",
    "procedure",
    "project",
    "todo",
    "warning",
]

def _format_tag_block_label(tag: str) -> str:
    return f"{tag.capitalize()} Memories"

def query_memories_by_tag_blocks(
    query: str,
    *,
    limits_by_tag: Dict[str, int],
    user_id: Optional[str] = None,
    include_tags: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Return an LLM-ready memory block per tag.

    Parameters
    ----------
    query:
        The user query / question.
    limits_by_tag:
        Dict mapping tag -> max results (k). Tags with k<=0 will return an
        empty block string.
    user_id:
        Optional override user id.
    include_tags:
        Optional subset of tags to retrieve. If omitted, uses ALLOWED_MEMORY_TAGS.

    Returns
    -------
    Dict[str, str]:
        Mapping tag -> formatted memory block string.
    """
    if user_id is None:
        user_id = get_default_user_id()

    tags_to_use = include_tags or ALLOWED_MEMORY_TAGS

    blocks: Dict[str, str] = {}
    for tag in tags_to_use:
        k = int(limits_by_tag.get(tag, 0) or 0)
        if k <= 0:
            blocks[tag] = ""
            continue

        raw = _query_memories_raw(
            query,
            k=k,
            user_id=user_id,
            tags=[tag],
        )
        blocks[tag] = _format_memories_block(_format_tag_block_label(tag), query, raw)

    return blocks


# ---------------------------------------------------------------------------
# Public API: retrieval functions that return TEXT
# ---------------------------------------------------------------------------

def query_memories(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
    sectors: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    label: str = "Memories",
) -> str:
    """
    High-level retrieval function for llm-thalamus.
    """
    raw = _query_memories_raw(
        query,
        k=k,
        user_id=user_id,
        sectors=sectors,
        tags=tags,
    )
    return _format_memories_block(label, query, raw)


def query_semantic(
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """
    Retrieve semantic-style memories and return them as an LLM-ready text block.
    """
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
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """
    Retrieve episodic-style memories and return them as an LLM-ready text block.
    """
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
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """
    Retrieve procedural-style memories and return them as an LLM-ready text block.
    """
    return query_memories(
        query,
        k=k,
        user_id=user_id,
        sectors=["procedural"],
        tags=tags,
        label="Procedural Memories",
    )


# ---------------------------------------------------------------------------
# Optional: CLI debugging helper
# ---------------------------------------------------------------------------

def print_memories(label: str, query: str, text_block: str) -> None:
    """
    Simple helper to print the text block returned by query_* functions
    with an additional top-level label. Mostly for CLI debugging.
    """
    print(f"\n=== {label} ===")
    print(text_block)
