from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Minimal final node logic for now:
      - pick the configured final model
      - build the prompt (user_input only)
    """
    model = deps.models["final"]
    prompt = state["task"]["user_input"]
    return model, prompt
