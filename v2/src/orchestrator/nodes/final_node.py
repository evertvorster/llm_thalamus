from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def run_final(state: State, deps: Deps) -> State:
    """
    Stub final node. No LLM calls yet.

    This exists to prove:
    - state contract wiring
    - deps/model selection wiring (final is mandatory)
    - event streaming plumbing (runner emits node_start/node_end/final)
    """
    model = deps.models["final"]
    user_text = state["task"]["user_input"]

    # Minimal deterministic behavior.
    answer = f"[stub final via model={model}] {user_text}"

    state["final"]["answer"] = answer
    state["runtime"]["node_trace"].append("final:stub")
    return state
