from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_router_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Router builds the plan:
      - intent
      - constraints
      - language
      - retrieval_k (0..max)
      - world_view ("none" | "time" | "full")

    Router does NOT need payloads. It only needs to know what it *can* request.
    """
    if "router" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.router is required for router node")

    model = deps.models["router"]
    user_input = state["task"]["user_input"]

    capabilities = (
        "[CAPABILITIES]\n"
        "- memory_retrieval: can fetch top-K relevant memories about the user/project.\n"
        "- world_view: can fetch 'time' (now,tz) or 'full' (now,tz,topics,goals,project).\n"
        "- tools: more tools (e.g. MCP) will exist later; request them only if needed.\n"
    )

    prompt = deps.prompt_loader.render(
        "router",
        user_input=user_input,
        capabilities=capabilities,
        world="",  # reserved
    )
    return model, prompt
