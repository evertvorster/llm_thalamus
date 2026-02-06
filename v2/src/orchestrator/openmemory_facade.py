from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from thalamus_openmemory.api.reader import search_memories
from thalamus_openmemory.api.writer import add_memory


@dataclass(frozen=True)
class OpenMemoryFacade:
    """
    Thin boundary around OpenMemory that:
      - exposes a minimal API to the orchestrator
      - does NOT accept or pass user_id

    Assumption (your stated design):
      - OpenMemory is configured at startup (bootstrap) and applies user scoping internally.
      - Therefore callers must never pass user_id.
    """
    _client: Any

    def search(self, query: str, *, k: int) -> List[Dict[str, Any]]:
        # Intentionally do NOT pass user_id.
        return search_memories(
            self._client,
            query=query,
            k=k,
        )

    def add(self, text: str) -> Dict[str, Any]:
        # Intentionally do NOT pass user_id.
        return add_memory(
            self._client,
            text,
        )
