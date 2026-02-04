from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import OpenMemoryClient
from .sync import run_async


def search_memories(
    client: OpenMemoryClient,
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Synchronous convenience wrapper around OpenMemoryClient.search().
    """
    return run_async(client.search(query, k=k, user_id=user_id))


async def search_memories_async(
    client: OpenMemoryClient,
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Async wrapper (use this inside async controller flows).
    """
    return await client.search(query, k=k, user_id=user_id)
