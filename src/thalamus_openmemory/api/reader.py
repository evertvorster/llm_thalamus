from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from .client import OpenMemoryClient
from .sync import run_async


def _is_sdk_memory_client(obj: object) -> bool:
    """
    Detect the upstream OpenMemory SDK client type (`openmemory.main.Memory`)
    without importing it at module import time.
    """
    t = type(obj)
    return (t.__module__ == "openmemory.main") and (t.__name__ == "Memory")


def search_memories(
    client: OpenMemoryClient,
    query: str,
    *,
    k: int = 10,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Synchronous convenience wrapper around OpenMemoryClient.search().

    NOTE:
    - Our API uses `k` (top-k).
    - The upstream SDK `openmemory.main.Memory.search()` uses `limit`.
      If the raw SDK client is passed in directly, map k -> limit.
    """
    if _is_sdk_memory_client(client):
        # openmemory.main.Memory.search(query, user_id=None, limit=10, **kwargs)
        sdk = cast(Any, client)
        return run_async(sdk.search(query, user_id=user_id, limit=k))

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

    NOTE:
    - Our API uses `k` (top-k).
    - The upstream SDK `openmemory.main.Memory.search()` uses `limit`.
      If the raw SDK client is passed in directly, map k -> limit.
    """
    if _is_sdk_memory_client(client):
        sdk = cast(Any, client)
        return await sdk.search(query, user_id=user_id, limit=k)

    return await client.search(query, k=k, user_id=user_id)
