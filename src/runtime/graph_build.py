from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.state import State
from runtime.registry import get
from runtime.nodes import context_bootstrap  # noqa: F401
from runtime.nodes import llm_primary_agent  # noqa: F401
from runtime.nodes import llm_reflect_topics  # noqa: F401
from runtime.nodes import llm_reflect_memory  # noqa: F401


def build_compiled_graph(deps, services):
    g = StateGraph(State)

    # Nodes
    g.add_node("context_bootstrap", get("context.bootstrap").make(deps, services))
    g.add_node("primary_agent", get("llm.primary_agent").make(deps, services))
    g.add_node("reflect_topics", get("llm.reflect_topics").make(deps, services))
    g.add_node("reflect_memory", get("llm.reflect_memory").make(deps, services))

    # Entry
    g.set_entry_point("context_bootstrap")

    # Bootstrap always feeds the primary planner/respond node.
    g.add_edge("context_bootstrap", "primary_agent")

    # Post-response persistence
    g.add_edge("primary_agent", "reflect_topics")
    g.add_edge("reflect_topics", "reflect_memory")
    g.add_edge("reflect_memory", END)

    return g.compile()
