# src/tests/langgraph_test_ollama_router.py
from __future__ import annotations

import json
from typing import TypedDict, Literal, Optional

import requests
from langgraph.graph.state import StateGraph
from langgraph.graph import END


# --- config for this spike ---
OLLAMA_URL = "http://localhost:11434"
ROUTER_MODEL = "qwen2.5:7b"     # fast, non-thinking (good router)
PLANNER_MODEL = "deepseek-r1:14b"  # only used if you later swap the dummy planner for an LLM


class LGState(TypedDict, total=False):
    user_text: str
    route: Literal["DIRECT", "PLAN"]
    answer: str
    trace: list[str]


def call_ollama_generate(prompt: str, model: str, *, stream: bool = False, timeout_s: int = 300) -> str:
    """
    Minimal Ollama /api/generate wrapper for spike testing.
    Uses non-streaming by default to reduce variables.
    """
    url = OLLAMA_URL.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
    }

    r = requests.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def parse_router_decision(text: str) -> Literal["DIRECT", "PLAN"]:
    """
    Router is constrained to output DIRECT or PLAN.
    Be defensive: accept lowercase and extra whitespace.
    Default to DIRECT if it outputs nonsense (router should be reliable).
    """
    t = (text or "").strip().upper()

    # Allow accidental punctuation/newlines
    t = t.split()[0] if t else ""

    if t == "PLAN":
        return "PLAN"
    return "DIRECT"


def node_route_llm(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("route_llm:enter")

    user_text = state["user_text"]

    # Keep router prompt very strict and short.
    prompt = (
        "You are a routing classifier for a local assistant.\n"
        "Return exactly one token: DIRECT or PLAN.\n"
        "DIRECT = the user just wants a straightforward reply.\n"
        "PLAN = the user is asking for multi-step reasoning, a design, or a plan.\n"
        "\n"
        f"User message:\n{user_text}\n"
        "\n"
        "Decision (DIRECT|PLAN):"
    )

    raw = call_ollama_generate(prompt, ROUTER_MODEL, stream=False)
    decision = parse_router_decision(raw)

    trace.append(f"route_llm:raw={raw!r}")
    trace.append(f"route_llm:decision={decision}")
    return {"route": decision, "trace": trace}


def node_answer_direct(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_direct:enter")

    # Dummy direct answer (no LLM yet)
    answer = f"[DIRECT] {state['user_text']}"

    trace.append("answer_direct:exit")
    return {"answer": answer, "trace": trace}


def node_answer_plan(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_plan:enter")

    # Dummy plan answer (no LLM yet)
    answer = f"[PLAN] {state['user_text']}"

    trace.append("answer_plan:exit")
    return {"answer": answer, "trace": trace}


def build_graph():
    g = StateGraph(LGState)

    g.add_node("route_llm", node_route_llm)
    g.add_node("answer_direct", node_answer_direct)
    g.add_node("answer_plan", node_answer_plan)

    g.set_entry_point("route_llm")

    def choose_next(state: LGState) -> str:
        return "answer_plan" if state.get("route") == "PLAN" else "answer_direct"

    g.add_conditional_edges("route_llm", choose_next, {
        "answer_direct": "answer_direct",
        "answer_plan": "answer_plan",
    })

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
        "Design a config layout for multiple LLM roles in Thalamus",
        "How are you?",
        "I need a multi-step troubleshooting plan for my Arch system",
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
