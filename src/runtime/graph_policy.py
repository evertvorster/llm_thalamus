from __future__ import annotations

from .state import State


def route_after_router(state: State) -> str:
    # Router stores next node in bootstrap scratch
    nxt = state.get("_next_node")
    return str(nxt or "answer")
