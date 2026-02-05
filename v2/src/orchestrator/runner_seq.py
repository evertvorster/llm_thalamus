from __future__ import annotations

from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.final_node import run_final
from orchestrator.state import State


def run_turn_seq(state: State, deps: Deps) -> Iterator[Event]:
    """
    Sequential runner (pre-LangGraph). Emits events for the worker to forward.

    For now it runs only the final node (stub) to prove the integration seam.
    """
    yield {"type": "node_start", "node": "final"}

    state = run_final(state, deps)

    yield {"type": "node_end", "node": "final"}

    answer = state["final"]["answer"]
    yield {"type": "final", "answer": answer}
