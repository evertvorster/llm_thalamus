from __future__ import annotations

from langgraph.graph import END, StateGraph

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.graph_nodes import (
    make_node_back_to_router,
    make_node_chat_messages,
    make_node_codegen,
    make_node_codegen_gate,
    make_node_episode_query,
    make_node_executor,
    make_node_final,
    make_node_memory_retrieval,
    make_node_planner,
    make_node_router,
    make_node_world_fetch,
    make_node_world_prefetch,
)
from orchestrator.graph_policy import (
    route_after_chat,
    route_after_codegen_gate,
    route_after_episode_query,
    route_after_executor,
    route_after_memory_retrieval,
    route_after_planner,
    route_after_router,
    route_after_world,
)
from orchestrator.state import State


def build_compiled_graph(deps: Deps, emit) -> object:
    g: StateGraph = StateGraph(State)

    # node wrappers (preserve event stream)
    g.add_node("world_prefetch", make_node_world_prefetch(deps, emit))
    g.add_node("router", make_node_router(deps, emit))

    # direct-mode nodes
    g.add_node("chat_messages", make_node_chat_messages(deps, emit))
    g.add_node("episode_query", make_node_episode_query(deps, emit))
    g.add_node("memory_retrieval", make_node_memory_retrieval(deps, emit))
    g.add_node("world_fetch", make_node_world_fetch(deps, emit))
    g.add_node("back_to_router", make_node_back_to_router())

    # incremental-mode nodes
    g.add_node("planner", make_node_planner(deps, emit))
    g.add_node("executor", make_node_executor(deps, emit))

    g.add_node("codegen_gate", make_node_codegen_gate())
    g.add_node("codegen", make_node_codegen(deps, emit))
    g.add_node("final", make_node_final(deps, emit))

    # entry point
    g.set_entry_point("world_prefetch")
    g.add_edge("world_prefetch", "router")

    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "planner": "planner",
            "chat_messages": "chat_messages",
            "episode_query": "episode_query",
            "memory_retrieval": "memory_retrieval",
            "world_fetch": "world_fetch",
            "codegen_gate": "codegen_gate",
        },
    )

    # incremental loop
    g.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "executor": "executor",
            "codegen_gate": "codegen_gate",
        },
    )
    g.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "planner": "planner",
        },
    )

    # direct-mode routing
    g.add_conditional_edges(
        "chat_messages",
        route_after_chat,
        {
            "episode_query": "episode_query",
            "memory_retrieval": "memory_retrieval",
            "world_fetch": "world_fetch",
            "back_to_router": "back_to_router",
            "codegen_gate": "codegen_gate",
        },
    )

    g.add_conditional_edges(
        "episode_query",
        route_after_episode_query,
        {
            "memory_retrieval": "memory_retrieval",
            "world_fetch": "world_fetch",
            "back_to_router": "back_to_router",
            "codegen_gate": "codegen_gate",
        },
    )

    g.add_conditional_edges(
        "memory_retrieval",
        route_after_memory_retrieval,
        {
            "episode_query": "episode_query",
            "world_fetch": "world_fetch",
            "back_to_router": "back_to_router",
            "codegen_gate": "codegen_gate",
        },
    )

    g.add_conditional_edges(
        "world_fetch",
        route_after_world,
        {
            "back_to_router": "back_to_router",
            "codegen_gate": "codegen_gate",
        },
    )

    g.add_edge("back_to_router", "router")

    g.add_conditional_edges(
        "codegen_gate",
        route_after_codegen_gate,
        {
            "codegen": "codegen",
            "final": "final",
        },
    )
    g.add_edge("codegen", "final")
    g.add_edge("final", END)

    return g.compile()


def run_graph(state: State, deps: Deps, emit) -> None:
    compiled = build_compiled_graph(deps, emit)
    emit({"type": "log", "text": "\n[langgraph] compiled.invoke(state)\n"})
    _ = compiled.invoke(state)
