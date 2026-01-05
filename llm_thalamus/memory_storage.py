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
- No tags or metadata are written; OpenMemory is expected to infer structure.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from openmemory.client import Memory


from memory_retrieval import get_memory as _get_memory  # canonical shared client
from memory_retrieval import run_om_async as _run_om_async



def get_memory() -> "Memory":
    """Return the shared OpenMemory Memory() instance."""
    return _get_memory()


def delete_memory(memory_id: str) -> None:
    """Permanently delete a memory (and its associated data) from OpenMemory."""
    mem = get_memory()
    _run_om_async(mem.delete(memory_id))


def store_memory(
    content: str,
    *,
    tags=None,  # tags are stored unmodified when provided
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy parameter retained for compatibility; ignored
) -> Dict[str, Any]:
    """
    Store an arbitrary memory item.

    Single-user system:
    - We do NOT write user_id.
    - tags are stored unmodified when provided by the caller.
    """
    mem = get_memory()
    return _run_om_async(mem.add(content))


def store_semantic(
    content: str,
    *,
    tags=None,  # legacy / ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy / ignored
) -> Dict[str, Any]:
    """Store a semantic-style memory (stable fact about the user or world)."""
    return store_memory(content)


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
    return store_memory(content)


def store_procedural(
    content: str,
    *,
    tags=None,  # legacy / ignored
    metadata: Optional[Dict[str, Any]] = None,
    user_id=None,  # legacy / ignored
    topic: Optional[str] = None,
) -> Dict[str, Any]:
    """Store a procedural-style memory (how-to / instructions)."""
    return store_memory(content)
