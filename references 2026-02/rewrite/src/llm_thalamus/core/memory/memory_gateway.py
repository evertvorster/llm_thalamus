from __future__ import annotations

from typing import Optional

from llm_thalamus.config.access import get_config
from llm_thalamus.core.memory.select_memories import query_memories_block


def retrieve_relevant_memories_text(
    query: str,
    *,
    k: Optional[int] = None,
    user_id: Optional[str] = None,
) -> str:
    """
    Read gateway for "LLM-facing memory text".

    Responsibilities:
    - choose default k from typed config if caller doesn't provide it
    - call the compatibility memory selection/formatting layer (select_memories.py)

    Notes:
    - This is a *read* surface only.
    - It is intentionally thin and easy to bypass later (e.g., MCP retrieval).
    """
    cfg = get_config()
    default_k = getattr(cfg, "max_memory_results", 8)

    if k is None:
        k = int(default_k)
    else:
        k = int(k)

    if k <= 0:
        return ""

    # user_id is optional; if omitted, select_memories will use default user id.
    return query_memories_block(query=query, k=k, user_id=user_id)
