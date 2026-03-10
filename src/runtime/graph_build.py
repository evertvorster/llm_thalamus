from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.state import State
from runtime.registry import get
from runtime.nodes import context_bootstrap  # noqa: F401
from runtime.nodes import llm_context_builder  # noqa: F401
from runtime.nodes import llm_answer  # noqa: F401
from runtime.nodes import llm_reflect  # noqa: F401


def build_compiled_graph(deps, services):
    g = StateGraph(State)

    # Nodes
    g.add_node("context_bootstrap", get("context.bootstrap").make(deps, services))
    g.add_node("context_builder", get("llm.context_builder").make(deps, services))
    g.add_node("answer", get("llm.answer").make(deps, services))
    g.add_node("reflect", get("llm.reflect").make(deps, services))

    # Entry
    g.set_entry_point("context_bootstrap")

    # Bootstrap always feeds the context builder
    g.add_edge("context_bootstrap", "context_builder")

    # Context builder decides the next step.
    # Route application is runtime-authoritative and explicit.
    def context_next_selector(state: State) -> str:
        rt = state.get("runtime") or {}
        if not isinstance(rt, dict):
            return "answer"

        nxt = rt.get("context_builder_route_node")
        if not isinstance(nxt, str):
            return "answer"

        nxt = nxt.strip().lower()

        if nxt == "answer":
            return "answer"

        return "answer"

    g.add_conditional_edges(
        "context_builder",
        context_next_selector,
        {
            "answer": "answer",
        },
    )

    # Post-answer persistence
    g.add_edge("answer", "reflect")
    g.add_edge("reflect", END)

    return g.compile()
