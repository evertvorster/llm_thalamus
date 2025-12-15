"""
Write-side helper module for llm-thalamus.

This module encapsulates:
- High-level helper functions to store memories

IMPORTANT:
- We delegate OpenMemory client construction/caching to memory_retrieval.get_memory()
  so there is exactly one OpenMemory instance per process and one consistent DB path.

Project policy (single-user + reduced tag semantics):
- user_id is ignored (single-user system).
- Tags are not a user-facing feature anymore.
- We DO attach a single internal tag on stored memories so sector-block retrieval
  can enforce "has at least one tag" without caring which tag it is.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from openmemory import OpenMemory

from memory_retrieval import get_memory as _get_memory  # canonical shared client


# A single internal tag is applied to every stored memory.
# This supports the "sector blocks only include tagged memories" rule
# without reintroducing tag taxonomies into the project.
_INTERNAL_TAG = ["thalamus"]


def get_memory() -> OpenMemory:
    """Return the shared OpenMemory instance."""
    return _get_memory()


def delete_memory(memory_id: str) -> None:
    """Permanently delete a memory (and its associated data) from OpenMemory."""
    mem = get_memory()
    mem.delete(memory_id)


def store_memory(
    content: str,
    *,
    tags=None,  # legacy parameter retained for compatibility; ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy parameter retained for compatibility; ignored
) -> Dict[str, Any]:
    """
    Store an arbitrary memory item.

    Single-user system:
    - We do NOT write userId.
    - We do NOT accept/propagate tag lists; we always attach one internal tag.
    """
    mem = get_memory()
    return mem.add(
        content,
        tags=_INTERNAL_TAG,
        metadata=metadata or {},
    )


def store_semantic(
    content: str,
    *,
    tags=None,  # legacy / ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy / ignored
) -> Dict[str, Any]:
    """Store a semantic-style memory (stable fact about the user or world)."""
    md = dict(metadata or {})
    md.setdefault("kind", "semantic")
    return store_memory(content, metadata=md)


def store_episodic(
    content: str,
    *,
    tags=None,  # legacy / ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy / ignored
    date: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """Store an episodic-style memory (a specific event in time)."""
    md = dict(metadata or {})
    md.setdefault("kind", "episodic")
    if date is not None:
        md.setdefault("date", date)
    if location is not None:
        md.setdefault("location", location)
    return store_memory(content, metadata=md)


def store_procedural(
    content: str,
    *,
    tags=None,  # legacy / ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy / ignored
    topic: Optional[str] = None,
) -> Dict[str, Any]:
    """Store a procedural-style memory (how-to / instructions)."""
    md = dict(metadata or {})
    md.setdefault("kind", "procedural")
    if topic is not None:
        md.setdefault("topic", topic)
    return store_memory(content, metadata=md)
