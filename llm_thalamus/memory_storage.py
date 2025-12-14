"""
Write-side helper module for llm-thalamus.

This module encapsulates:
- High-level helper functions to store memories

IMPORTANT:
- We delegate OpenMemory client construction/caching to memory_retrieval.get_memory()
  so there is exactly one OpenMemory instance per process and one consistent DB path.

NOTE (single-user local setup):
- We intentionally do NOT scope writes by user_id.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openmemory import OpenMemory

from memory_retrieval import get_memory as _get_memory  # canonical shared client
from memory_retrieval import get_default_user_id as _get_default_user_id


def get_memory() -> OpenMemory:
    """
    Return the shared OpenMemory instance.

    Delegates to memory_retrieval.get_memory() to ensure:
    - consistent DB path resolution
    - one cached client per process
    """
    return _get_memory()


def get_default_user_id() -> str:
    """Return the default user_id from config (retained for compatibility)."""
    return _get_default_user_id()


def delete_memory(memory_id: str) -> None:
    """
    Permanently delete a memory (and its associated data) from OpenMemory.
    """
    mem = get_memory()
    # OpenMemory delete is idempotent: deleting a non-existent id is safe.
    mem.delete(memory_id)


# ---------------------------------------------------------------------------
# Generic storage helper
# ---------------------------------------------------------------------------

def store_memory(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,  # retained for API compatibility; ignored
) -> Dict[str, Any]:
    """
    Store an arbitrary memory item.

    We rely on OpenMemory's automatic classification:
    - No manual sectors or primarySector.
    - content is the main input; tags/metadata just provide hints.

    NOTE:
    - In this project we run a single-user local DB, so we do NOT write userId.
    """
    mem = get_memory()

    result = mem.add(
        content,
        tags=tags or [],
        metadata=metadata or {},
    )
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
    user_id: Optional[str] = None,  # retained for API compatibility; ignored
) -> Dict[str, Any]:
    """
    Store a semantic-style memory (stable fact about the user or world).
    """
    tags = (tags or []) + ["semantic"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "semantic")
    return store_memory(content, tags=tags, metadata=metadata)


def store_episodic(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,  # retained for API compatibility; ignored
    date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store an episodic-style memory (a specific event in time).
    """
    tags = (tags or []) + ["episodic"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "episodic")
    if date is not None:
        metadata.setdefault("date", date)
    if location is not None:
        metadata.setdefault("location", location)
    return store_memory(content, tags=tags, metadata=metadata)


def store_procedural(
    content: str,
    *,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,  # retained for API compatibility; ignored
    topic: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a procedural-style memory (how-to / instructions).
    """
    tags = (tags or []) + ["procedural"]
    metadata = dict(metadata or {})
    metadata.setdefault("kind", "procedural")
    if topic is not None:
        metadata.setdefault("topic", topic)
    return store_memory(content, tags=tags, metadata=metadata)
