from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_router_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Router node logic:
      - choose router model
      - build prompt from resources/prompts/router.txt

    Note:
      Router does not need world state content by default. We still pass an empty
      'world' var so the prompt template may include {world} without KeyError.
    """
    if "router" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.router is required for router node")

    model = deps.models["router"]
    user_input = state["task"]["user_input"]

    prompt = deps.prompt_loader.render("router", user_input=user_input, world="")
    return model, prompt
