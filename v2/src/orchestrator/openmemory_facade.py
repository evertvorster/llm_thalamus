from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from thalamus_openmemory.api.reader import search_memories
from thalamus_openmemory.api.writer import add_memory


@dataclass(frozen=True)
class OpenMemoryFacade:
    """
    Thin boundary around OpenMemory that:
      - (optionally) binds user_id internally
      - hides user_id from orchestrator / nodes

    IMPORTANT:
      - Orchestrator/nodes must NEVER reference user_id.
      - user_id is an OpenMemory concern; it may be configured at startup.
      - If user_id is not set here, OpenMemory's default behavior applies.
    """
    _client: Any
    _user_id: Optional[str] = None

    def search(self, query: str, *, k: int) -> List[Dict[str, Any]]:
        kwargs = {"query": query, "k": k}
        if self._user_id:
            kwargs["user_id"] = self._user_id
        return search_memories(self._client, **kwargs)

    def add(self, text: str) -> Dict[str, Any]:
        kwargs = {}
        if self._user_id:
            kwargs["user_id"] = self._user_id
        return add_memory(self._client, text, **kwargs)
