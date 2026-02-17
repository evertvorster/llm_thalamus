from __future__ import annotations

from langgraph.graph import END, StateGraph

from orchestrator.deps import Deps
from orchestrator.state import State

from runtime.graph_policy import route_after_router
from runtime.registry import get

import runtime.nodes  # ensure registration side-effects


def build_compiled_graph(deps: Deps) -> object:
    g: StateGraph = StateGraph(State)

    router = get("llm.router").make(deps)
    answer = get("llm.answer").make(deps)

    g.add_node("router", router)
    g.add_node("answer", answer)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "answer": "answer",
        },
    )

    g.add_edge("answer", END)
    return g.compile()
