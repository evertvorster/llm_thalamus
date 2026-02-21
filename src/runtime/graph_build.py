from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.state import State
from runtime.registry import get
from runtime.nodes import llm_router  # noqa: F401
from runtime.nodes import llm_context_builder  # noqa: F401
from runtime.nodes import llm_world_modifier  # noqa: F401
from runtime.nodes import llm_answer  # noqa: F401
from runtime.nodes import llm_reflect_topics  # noqa: F401
from runtime.nodes import llm_memory_retriever  # noqa: F401
from runtime.nodes import llm_memory_writer  # noqa: F401


def build_compiled_graph(deps, services):
    g = StateGraph(State)

    # Nodes
    g.add_node("router", get("llm.router").make(deps, services))
    g.add_node("context_builder", get("llm.context_builder").make(deps, services))
    g.add_node("memory_retriever", get("llm.memory_retriever").make(deps, services))
    g.add_node("world_modifier", get("llm.world_modifier").make(deps, services))
    g.add_node("answer", get("llm.answer").make(deps, services))
    g.add_node("reflect_topics", get("llm.reflect_topics").make(deps, services))
    g.add_node("memory_writer", get("llm.memory_writer").make(deps, services))

    # Edges
    g.set_entry_point("router")

    def route_selector(state: State) -> str:
        r = (state.get("task") or {}).get("route")
        if r == "context":
            return "context_builder"
        if r == "world":
            return "world_modifier"
        return "answer"

    g.add_conditional_edges(
        "router",
        route_selector,
        {
            "context_builder": "context_builder",
            "world_modifier": "world_modifier",
            "answer": "answer",
        },
    )

    # context path now includes memory retrieval
    g.add_edge("context_builder", "memory_retriever")
    g.add_edge("memory_retriever", "answer")

    # world path unchanged
    g.add_edge("world_modifier", "answer")

    # end of turn: reflect, then write memories, then end
    g.add_edge("answer", "reflect_topics")
    g.add_edge("reflect_topics", "memory_writer")
    g.add_edge("memory_writer", END)

    return g.compile()