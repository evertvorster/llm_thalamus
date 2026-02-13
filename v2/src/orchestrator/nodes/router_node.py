from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_router_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Router is a cheap gate.

    It decides ONLY whether the user message should go directly to final ("final")
    or to the planner/executor loop ("planner").

    It does NOT:
      - request chat history
      - request memories
      - request episodic DB
      - select world_view
      - set retrieval_k
      - perform work

    Time is ALWAYS available via state["world"]["now"] / ["tz"].
    """
    if "router" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.router is required for router node")

    model = deps.models["router"]
    user_input = state["task"]["user_input"]

    w = state.get("world") or {}
    now = str(w.get("now", "") or "")
    tz = str(w.get("tz", "") or "")

    prompt = deps.prompt_loader.render(
        "router",
        user_input=user_input,
        now=now,
        tz=tz,
    )
    return model, prompt
