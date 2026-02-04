from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import OpenMemoryClient
from .sync import run_async


def add_memory(
    client: OpenMemoryClient,
    content: str,
    *,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Synchronous convenience wrapper around OpenMemoryClient.add().
    Returns the created memory payload (should contain an id).
    """
    return run_async(client.add(content, user_id=user_id, metadata=metadata, tags=tags))


async def add_memory_async(
    client: OpenMemoryClient,
    content: str,
    *,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return await client.add(content, user_id=user_id, metadata=metadata, tags=tags)


def delete_memory(client: OpenMemoryClient, memory_id: str) -> None:
    """
    Synchronous convenience wrapper around OpenMemoryClient.delete().
    """
    run_async(client.delete(memory_id))


async def delete_memory_async(client: OpenMemoryClient, memory_id: str) -> None:
    await client.delete(memory_id)
