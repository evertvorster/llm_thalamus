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

    # Context controller loop:
    # The context_builder decides the next step by writing a directive into state["context"].
    # Default behavior: go straight to answer when no directive is present.
    #
    # Supported directives (aliases):
    #   state["context"]["next"] / ["next_node"] / ["route"] == "memory_retriever" -> run memory retriever, then loop back
    #   ... == "answer" -> go to answer
    #
    # Future-proof: additional retrieval/action nodes can be added here later.
    def context_next_selector(state: State) -> str:
        ctx = state.get("context") or {}
        if not isinstance(ctx, dict):
            return "answer"

        # Optional safety guard against infinite loops.
        rt = state.get("runtime") or {}
        hops = rt.get("context_hops") if isinstance(rt, dict) else None
        try:
            if isinstance(hops, int) and hops >= 5:
                # Too many controller hops; fall back to answer.
                return "answer"
        except Exception:
            pass

        # Allow a few alias keys to reduce friction during prompt evolution.
        nxt = ctx.get("next")
        if not nxt:
            nxt = ctx.get("next_node")
        if not nxt:
            nxt = ctx.get("route")
        if not isinstance(nxt, str):
            nxt = ""

        nxt = nxt.strip()

        if nxt == "memory_retriever":
            return "memory_retriever"
        if nxt == "answer":
            return "answer"

        # Default: answer (do NOT run heavy retrievers unless explicitly requested).
        return "answer"

    g.add_conditional_edges(
        "context_builder",
        context_next_selector,
        {
            "memory_retriever": "memory_retriever",
            "answer": "answer",
        },
    )

    # If the controller requests memory retrieval, loop back to re-evaluate context.
    g.add_edge("memory_retriever", "context_builder")

    # world path unchanged
    g.add_edge("world_modifier", "answer")

    # end of turn: reflect, then write memories, then end
    g.add_edge("answer", "reflect_topics")
    g.add_edge("reflect_topics", "memory_writer")
    g.add_edge("memory_writer", END)

    return g.compile()