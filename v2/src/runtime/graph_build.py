from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.deps import Deps
from runtime.state import State
from runtime.registry import get

import runtime.nodes  # noqa: F401  (registration side-effects)


def build_compiled_graph(deps: Deps):
    g: StateGraph = StateGraph(State)

    router = get("llm.router").make(deps)
    answer = get("llm.answer").make(deps)

    g.add_node("router", router)
    g.add_node("answer", answer)

    g.set_entry_point("router")
    g.add_edge("router", "answer")
    g.add_edge("answer", END)

    return g.compile()
