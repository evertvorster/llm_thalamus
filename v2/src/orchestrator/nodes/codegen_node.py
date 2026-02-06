from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def run_codegen_stub(state: State, deps: Deps) -> State:
    """
    Codegen stub.

    For now:
      - does not generate code
      - only appends trace so we can prove branching works

    Later this node will:
      - build a code-oriented prompt
      - call deps.llm_generate_stream using the configured codegen model
      - write into state['draft']
    """
    _ = deps  # unused for now

    state["runtime"]["node_trace"].append("codegen:stub")
    return state
