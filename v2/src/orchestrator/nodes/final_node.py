from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Final node logic:
      - pick the configured final model
      - build the prompt from resources/prompts/final.txt
    """
    model = deps.models["final"]
    user_input = state["task"]["user_input"]

    prompt = deps.prompt_loader.render("final", user_input=user_input)
    return model, prompt
