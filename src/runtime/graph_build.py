from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.deps import Deps
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.registry import get

import runtime.nodes  # noqa: F401  (registration side-effects)


def build_compiled_graph(deps: Deps, services: RuntimeServices):
    g: StateGraph = StateGraph(State)

    router = get("llm.router").make(deps, services)
    context_builder = get("llm.context_builder").make(deps, services)
    answer = get("llm.answer").make(deps, services)
    reflect_topics = get("llm.reflect_topics").make(deps, services)

    g.add_node("router", router)
    g.add_node("context_builder", context_builder)
    g.add_node("answer", answer)
    g.add_node("reflect_topics", reflect_topics)

    g.set_entry_point("router")

    # --- first real branch: router decides answer vs context_builder ---
    def _route_from_state(state: State) -> str:
        route = (state.get("task", {}) or {}).get("route")  # type: ignore[assignment]
        if isinstance(route, str) and route.strip().lower() == "context":
            return "context"
        return "answer"

    g.add_conditional_edges(
        "router",
        _route_from_state,
        {
            "context": "context_builder",
            "answer": "answer",
        },
    )

    g.add_edge("context_builder", "answer")
    g.add_edge("answer", "reflect_topics")
    g.add_edge("reflect_topics", END)

    return g.compile()
