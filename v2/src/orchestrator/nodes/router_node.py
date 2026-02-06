from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_router_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Router node logic:
      - choose router model
      - build prompt from resources/prompts/router.txt
    """
    if "router" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.router is required for router node")

    model = deps.models["router"]
    user_input = state["task"]["user_input"]
    prompt = deps.prompt_loader.render("router", user_input=user_input)
    return model, prompt
