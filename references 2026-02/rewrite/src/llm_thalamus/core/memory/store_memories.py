from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm_thalamus.adapters.openmemory.client import add, delete, get_default_user_id


def store_memory(
    content: str,
    *,
    user_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Any:
    """
    Store a memory via OpenMemory.

    Behavior preserved from old code:
    - passes metadata/tags through if provided
    - defaults user_id from config if not provided
    """
    uid = user_id or get_default_user_id()
    return add(
        content,
        user_id=uid,
        memory_type=memory_type,
        metadata=metadata,
        tags=tags,
    )


def store_semantic_memory(
    content: str,
    *,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Any:
    return store_memory(
        content,
        user_id=user_id,
        memory_type="semantic",
        metadata=metadata,
        tags=tags,
    )


def store_episodic_memory(
    content: str,
    *,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Any:
    return store_memory(
        content,
        user_id=user_id,
        memory_type="episodic",
        metadata=metadata,
        tags=tags,
    )


def delete_memory(memory_id: str) -> None:
    delete(memory_id)
