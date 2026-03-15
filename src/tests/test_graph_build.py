from __future__ import annotations

from runtime.graph_build import build_compiled_graph
from runtime.graph_policy import route_after_router


def test_default_graph_path_uses_primary_agent_then_reflect() -> None:
    compiled = build_compiled_graph(None, None)
    graph = compiled.get_graph()

    node_ids = set(graph.nodes.keys())
    assert "context_bootstrap" in node_ids
    assert "primary_agent" in node_ids
    assert "reflect" in node_ids

    edges = {(edge.source, edge.target, bool(edge.conditional)) for edge in graph.edges}
    assert ("__start__", "context_bootstrap", False) in edges
    assert ("context_bootstrap", "primary_agent", False) in edges
    assert ("primary_agent", "reflect", False) in edges
    assert ("reflect", "__end__", False) in edges

    assert ("context_bootstrap", "context_builder", False) not in edges
    assert ("context_builder", "answer", True) not in edges
    assert ("answer", "reflect", False) not in edges


def test_router_fallback_defaults_to_primary_agent() -> None:
    assert route_after_router({}) == "primary_agent"
