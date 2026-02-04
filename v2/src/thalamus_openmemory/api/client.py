from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


class OpenMemoryError(RuntimeError):
    pass


class OpenMemoryClient(Protocol):
    """
    Runtime-facing OpenMemory client interface.

    This package is config-blind: it does NOT know whether the backend is sqlite,
    MCP, HTTP, etc. That is the bootstrap’s job.
    """

    async def add(
        self,
        content: str,
        *,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]: ...

    async def search(
        self,
        query: str,
        *,
        k: int = 10,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    async def delete(self, memory_id: str) -> None: ...


@dataclass(frozen=True)
class OpenMemoryHealth:
    ok: bool
    details: str = ""
