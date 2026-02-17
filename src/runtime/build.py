from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.deps import Deps
from runtime.registry import get
from runtime.state import State

# Ensure node modules are imported (registered) before build.
import runtime.nodes  # noqa: F401


def build_compiled_graph(deps: Deps, emit) -> object:
    """
    Bootstrap graph:
      entry -> llm.router -> llm.answer -> END
    """
    g: StateGraph = StateGraph(State)

    router = get("llm.router").make(deps)
    answer = get("llm.answer").make(deps)

    g.add_node("router", router)
    g.add_node("answer", answer)

    g.set_entry_point("router")
    g.add_edge("router", "answer")
    g.add_edge("answer", END)

    return g.compile()


def run_graph(state: State, deps: Deps, emit) -> State:
    compiled = build_compiled_graph(deps, emit)
    return compiled.invoke(state)
