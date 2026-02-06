from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def run_retrieval_stub(state: State, deps: Deps) -> State:
    """
    Retrieval stub.

    For now:
      - does not call OpenMemory / filesystem
      - only appends trace so we can prove branching works

    Later this node will:
      - query OpenMemory
      - normalize results into state['context']
      - append tool call audit entries
    """
    _ = deps  # unused for now

    state["runtime"]["node_trace"].append("retrieval:stub")
    return state
