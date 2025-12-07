"""
memory_storage.py

Write-side helper module for llm-thalamus.

This module encapsulates:
- Loading config/config.json
- Constructing an OpenMemory client (local SQLite + Ollama embeddings)
- High-level helper functions to store memories

We ALWAYS trust OpenMemory's advanced automatic memory interface:
- We never manually set sectors or primarySector.
- We only provide content, tags, metadata, and userId.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from openmemory import OpenMemory

# Path to the shared config file
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.json"

# Simple module-level cache for the OpenMemory instance
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

    return OpenMemory(
        path=om_cfg["path"],
        tier=om_cfg.get("tier", "smart"),
        embeddings=embeddings,
    )


def get_memory() -> OpenMemory:
    """
    Return a shared OpenMemory instance.

    This is a small convenience so that:
    - We only construct the client once per process.
    - All store/recall operations share the same underlying connection.
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
# Generic storage helper
# ---------------------------------------------------------------------------

def store_memory(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store an arbitrary memory item.

    We rely on OpenMemory's automatic classification:
    - No manual sectors or primarySector.
    - content is the main input; tags/metadata just provide hints.

    Parameters
    ----------
    content:
        The natural-language text of the memory.
    tags:
        Optional list of tags, e.g. ["persona", "llm-thalamus"].
    metadata:
        Optional metadata dict (JSON-serializable) for additional structure.
    user_id:
        Optional user identifier. If omitted, uses config.thalamus.default_user_id.

    Returns
    -------
    dict
        The OpenMemory result (id, content/text, primarySector, sectors, etc.).
    """
    mem = get_memory()
    if user_id is None:
        user_id = get_default_user_id()

    result = mem.add(
        content,
        tags=tags or [],
        metadata=metadata or {},
        userId=user_id,
    )
    # We do not rely on the exact structure, but return it in case callers care.
    return result


# ---------------------------------------------------------------------------
# Convenience helpers for common “styles” of memory
# (semantic / episodic / procedural)
# ---------------------------------------------------------------------------

def store_semantic(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a semantic-style memory (stable fact about the user or world).

    We don't force a sector; we just:
    - Add a 'semantic' marker in tags/metadata to help with filtering later.
    """
    tags = (tags or []) + ["semantic"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "semantic")
    return store_memory(content, tags=tags, metadata=metadata, user_id=user_id)


def store_episodic(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store an episodic-style memory (a specific event in time).

    Parameters like `date` and `location` are optional helpers; when provided,
    they are added into metadata.
    """
    tags = (tags or []) + ["episodic"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "episodic")
    if date is not None:
        metadata.setdefault("date", date)
    if location is not None:
        metadata.setdefault("location", location)
    return store_memory(content, tags=tags, metadata=metadata, user_id=user_id)


def store_procedural(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    topic: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a procedural-style memory (how-to / instructions).

    The `topic` field is added to metadata when provided, so we can later
    filter and search for procedures on that topic.
    """
    tags = (tags or []) + ["procedural"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "procedural")
    if topic is not None:
        metadata.setdefault("topic", topic)
    return store_memory(content, tags=tags, metadata=metadata, user_id=user_id)
