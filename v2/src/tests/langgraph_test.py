from __future__ import annotations

from typing import TypedDict, Literal, Optional

from langgraph.graph.state import StateGraph
from langgraph.graph import END


class LGState(TypedDict, total=False):
    user_text: str
    route: Literal["direct", "plan"]
    answer: str
    trace: list[str]


def node_route(state: LGState) -> LGState:
    """Dummy router: decide route without any LLM."""
    text = state["user_text"]
    trace = state.get("trace", [])
    trace.append("route:enter")

    # Super dumb heuristic just to test branching.
    route: Literal["direct", "plan"] = "plan" if "plan" in text.lower() else "direct"

    trace.append(f"route:decision={route}")
    return {"route": route, "trace": trace}


def node_answer_direct(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_direct:enter")
    answer = f"[DIRECT] {state['user_text']}"
    trace.append("answer_direct:exit")
    return {"answer": answer, "trace": trace}


def node_answer_plan(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_plan:enter")
    answer = f"[PLAN] {state['user_text']}"
    trace.append("answer_plan:exit")
    return {"answer": answer, "trace": trace}


def build_graph():
    g = StateGraph(LGState)

    g.add_node("route", node_route)
    g.add_node("answer_direct", node_answer_direct)
    g.add_node("answer_plan", node_answer_plan)

    g.set_entry_point("route")

    def choose_next(state: LGState) -> str:
        # Return the next node name
        return "answer_plan" if state.get("route") == "plan" else "answer_direct"

    g.add_conditional_edges("route", choose_next, {
        "answer_direct": "answer_direct",
        "answer_plan": "answer_plan",
    })

    # Both answer nodes terminate the graph.
    g.add_edge("answer_direct", END)
    g.add_edge("answer_plan", END)

    return g.compile()


def run_once(app, text: str) -> LGState:
    initial: LGState = {"user_text": text, "trace": []}
    out = app.invoke(initial)
    return out


def main() -> int:
    app = build_graph()

    tests = [
        "Hello there",
        "Please plan this for me",
        "PLAN: make a route",  # should route to plan
    ]

    for t in tests:
        out = run_once(app, t)
        print("\n=== INPUT ===")
        print(t)
        print("=== OUTPUT ===")
        print("route:", out.get("route"))
        print("answer:", out.get("answer"))
        print("trace:", " -> ".join(out.get("trace", [])))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
