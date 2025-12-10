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
from pathlib import Path
from typing import Any, Dict, List, Optional
from paths import get_user_config_path

from openmemory import OpenMemory

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

    from pathlib import Path  # already imported at top
    om_raw_path = om_cfg["path"]
    om_path = Path(om_raw_path).expanduser()
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

    Structure example:

    ### Semantic Memories
    Query: Where does Evert live?

    [1]
    Score: 0.93
    PrimarySector: semantic
    Tags: [...]
    Content: ...

    [2]
    ...
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

    Returns a single **string** containing nicely formatted memories,
    ready to be dropped into an LLM prompt.

    If you ever need the raw structured data instead, call _query_memories_raw().
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
