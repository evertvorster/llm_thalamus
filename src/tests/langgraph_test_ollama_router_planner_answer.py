# src/tests/langgraph_test_ollama_router_planner_answer.py
from __future__ import annotations

import json
from typing import TypedDict, Literal

import requests
from langgraph.graph.state import StateGraph
from langgraph.graph import END


# --- config for this spike ---
OLLAMA_URL = "http://localhost:11434"

ROUTER_MODEL = "qwen2.5:7b"        # fast router
PLANNER_MODEL = "deepseek-r1:14b"  # thinking-capable
CHAT_MODEL = "qwen2.5:14b"         # user-facing answer


class LGState(TypedDict, total=False):
    user_text: str
    route: Literal["DIRECT", "PLAN"]

    # planner outputs
    plan: str
    plan_thinking: str

    # final answer
    answer: str

    # debug trace
    trace: list[str]


def call_ollama_generate(prompt: str, model: str, *, timeout_s: int = 300) -> str:
    """Non-streaming /api/generate wrapper."""
    url = OLLAMA_URL.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = requests.post(url, json=payload, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def call_ollama_stream(prompt: str, model: str, *, timeout_s: int = 300) -> tuple[str, str]:
    """
    Streaming /api/generate wrapper.
    Returns: (response_text, thinking_text)
    """
    url = OLLAMA_URL.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": True}

    response_parts: list[str] = []
    thinking_parts: list[str] = []

    # timeout=(connect, read)
    r = requests.post(url, json=payload, timeout=(10, timeout_s), stream=True)
    r.raise_for_status()

    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue

        try:
            data = json.loads(line)
        except Exception as e:
            raise RuntimeError(f"Malformed Ollama stream line: {line!r}") from e

        if data.get("error"):
            raise RuntimeError(str(data.get("error")))

        thinking_tok = data.get("thinking")
        if thinking_tok:
            thinking_parts.append(str(thinking_tok))

        resp_tok = data.get("response")
        if resp_tok:
            response_parts.append(str(resp_tok))

        if data.get("done") is True:
            break

    return ("".join(response_parts).strip(), "".join(thinking_parts))


def parse_router_decision(text: str) -> Literal["DIRECT", "PLAN"]:
    t = (text or "").strip().upper()
    t = t.split()[0] if t else ""
    if t == "PLAN":
        return "PLAN"
    return "DIRECT"


# ---------------- nodes ----------------

def node_route_llm(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("route_llm:enter")

    user_text = state["user_text"]
    prompt = (
        "You are a routing classifier for a local assistant.\n"
        "Return exactly one token: DIRECT or PLAN.\n"
        "DIRECT = straightforward reply.\n"
        "PLAN = multi-step reasoning, design, or troubleshooting.\n"
        "\n"
        f"User message:\n{user_text}\n"
        "\n"
        "Decision (DIRECT|PLAN):"
    )

    raw = call_ollama_generate(prompt, ROUTER_MODEL)
    decision = parse_router_decision(raw)

    trace.append(f"route_llm:raw={raw!r}")
    trace.append(f"route_llm:decision={decision}")
    return {"route": decision, "trace": trace}


def node_answer_direct_llm(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_direct_llm:enter")

    user_text = state["user_text"]
    prompt = (
        "You are a helpful assistant. Reply concisely and directly.\n"
        f"User: {user_text}\n"
        "Assistant:"
    )
    answer = call_ollama_generate(prompt, CHAT_MODEL)

    trace.append("answer_direct_llm:exit")
    return {"answer": answer, "trace": trace}


def node_planner_llm(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("planner_llm:enter")

    user_text = state["user_text"]
    prompt = (
        "You are a planning assistant.\n"
        "Produce a short, actionable plan as bullet points.\n"
        "Do NOT write the final user-facing answer.\n"
        "\n"
        f"Task:\n{user_text}\n"
        "\n"
        "Plan:"
    )

    plan_text, thinking_text = call_ollama_stream(prompt, PLANNER_MODEL)

    trace.append(f"planner_llm:thinking_chars={len(thinking_text)}")
    trace.append("planner_llm:exit")
    return {"plan": plan_text, "plan_thinking": thinking_text, "trace": trace}


def node_answer_from_plan_llm(state: LGState) -> LGState:
    trace = state.get("trace", [])
    trace.append("answer_from_plan_llm:enter")

    user_text = state["user_text"]
    plan = state.get("plan", "").strip()

    prompt = (
        "You are a helpful assistant.\n"
        "Use the plan to write a concise, clear answer.\n"
        "Do not mention the existence of the plan.\n"
        "\n"
        f"User request:\n{user_text}\n"
        "\n"
        f"Internal plan:\n{plan}\n"
        "\n"
        "Assistant:"
    )

    answer = call_ollama_generate(prompt, CHAT_MODEL)

    trace.append("answer_from_plan_llm:exit")
    return {"answer": answer, "trace": trace}


# ---------------- graph ----------------

def build_graph():
    g = StateGraph(LGState)

    g.add_node("route_llm", node_route_llm)
    g.add_node("answer_direct_llm", node_answer_direct_llm)
    g.add_node("planner_llm", node_planner_llm)
    g.add_node("answer_from_plan_llm", node_answer_from_plan_llm)

    g.set_entry_point("route_llm")

    def choose_after_route(state: LGState) -> str:
        return "planner_llm" if state.get("route") == "PLAN" else "answer_direct_llm"

    g.add_conditional_edges("route_llm", choose_after_route, {
        "planner_llm": "planner_llm",
        "answer_direct_llm": "answer_direct_llm",
    })

    g.add_edge("planner_llm", "answer_from_plan_llm")
    g.add_edge("answer_direct_llm", END)
    g.add_edge("answer_from_plan_llm", END)

    return g.compile()


def run_once(app, text: str) -> LGState:
    initial: LGState = {"user_text": text, "trace": []}
    return app.invoke(initial)


def main() -> int:
    print("Router model :", ROUTER_MODEL)
    print("Planner model:", PLANNER_MODEL)
    print("Chat model   :", CHAT_MODEL)

    app = build_graph()

    tests = [
        "Hello there",
        "I need a multi-step troubleshooting plan for my Arch system",
        "Design a config layout for multiple LLM roles in Thalamus",
    ]

    for t in tests:
        out = run_once(app, t)

        print("\n=== INPUT ===")
        print(t)

        print("=== ROUTE ===")
        print(out.get("route"))

        if out.get("route") == "PLAN":
            thinking = out.get("plan_thinking", "")
            plan = out.get("plan", "")
            print("=== THINKING (len) ===")
            print(len(thinking))
            print("=== PLAN ===")
            print(plan)

        print("=== ANSWER ===")
        print(out.get("answer"))

        print("=== TRACE ===")
        print(" -> ".join(out.get("trace", [])))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
