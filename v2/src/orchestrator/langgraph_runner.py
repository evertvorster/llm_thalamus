from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Callable

from langgraph.graph import END, StateGraph

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.codegen_node import run_codegen_stub
from orchestrator.nodes.final_node import build_final_request
from orchestrator.nodes.retrieval_node import run_retrieval_node
from orchestrator.nodes.router_node import build_router_request
from orchestrator.state import State


_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}


def _extract_json_object(text: str) -> str:
    """Extract the first JSON object from a string."""
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in router output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("unterminated JSON object in router output")


def _parse_router_output(raw: str) -> dict:
    """
    Parse the router model output.

    Expected JSON object keys:
      - intent: one of qa/coding/planning/research/ops
      - constraints: list[str]
      - language: str (e.g. "en")
    """
    blob = _extract_json_object(raw)
    data = json.loads(blob)

    intent = (data.get("intent") or "").strip().lower()
    if not intent or intent not in _ALLOWED_INTENTS:
        intent = "qa"

    constraints = data.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []

    language = (data.get("language") or "").strip().lower() or "en"

    return {"intent": intent, "constraints": constraints, "language": language}


def _collect_streamed_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None],
) -> str:
    """
    Stream from deps.llm_generate_stream, emitting 'log' events as chunks arrive.
    Returns only the concatenated "response" chunks (not "thinking").
    """
    response_parts: list[str] = []

    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue

        # Forward both thinking + response for UI visibility
        emit({"type": "log", "text": text})

        if kind == "response":
            response_parts.append(text)

    return "".join(response_parts).strip()


def _wants_retrieval(state: State, deps: Deps) -> bool:
    """
    Retrieval is opt-in per turn.

    Router sets state["task"]["retrieval_k"].
    If it is missing/None/0, retrieval is skipped.
    """
    k = state.get("task", {}).get("retrieval_k")
    try:
        k_int = int(k or 0)
    except Exception:
        k_int = 0
    return k_int > 0


def _wants_codegen(state: State) -> bool:
    return state["task"]["intent"] == "coding"


def run_turn_langgraph(state: State, deps: Deps) -> Iterator[Event]:
    """
    Execute the *compiled* LangGraph graph while preserving your existing streaming Event protocol.

    - Nodes emit:
        node_start/node_end/log/final
      into a queue.
    - This generator yields events live to the caller (ControllerWorker).

    Reflection is intentionally NOT part of this graph (project rule).
    """
    q: queue.Queue[Event | None] = queue.Queue()

    def emit(ev: Event) -> None:
        q.put(ev)

    # ----------------------
    # LangGraph node callables
    # ----------------------

    def node_router(s: State) -> State:
        emit({"type": "node_start", "node": "router"})
        model, prompt = build_router_request(s, deps)
        raw = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)

        parsed = _parse_router_output(raw)
        s["task"]["intent"] = parsed["intent"]
        s["task"]["constraints"] = parsed["constraints"]
        s["task"]["language"] = parsed["language"]

        # Router-level retrieval decision (opt-in).
        # Default policy: only retrieve for research/ops unless you expand router schema later.
        default_k = int(deps.cfg.orchestrator_retrieval_default_k)
        if s["task"]["intent"] in {"research", "ops"} and default_k > 0:
            s["task"]["retrieval_k"] = default_k
        else:
            s["task"]["retrieval_k"] = 0

        emit({"type": "node_end", "node": "router"})
        return s

    def node_retrieval(s: State) -> State:
        # Use the per-turn retrieval_k selected by router.
        emit({"type": "node_start", "node": "retrieval"})
        out = run_retrieval_node(s, deps)

        mems = out.get("context", {}).get("memories", []) or []
        emit({"type": "log", "text": f"\n[retrieval] memories={len(mems)}\n"})
        for m in mems[:3]:
            txt = str(m.get("text", "") or "")
            if txt:
                emit({"type": "log", "text": f"- {txt[:200]}\n"})

        out["runtime"]["node_trace"].append("retrieval:openmemory")
        emit({"type": "node_end", "node": "retrieval"})
        return out

    def node_codegen_gate(s: State) -> State:
        # Pure gate node; no events. Keeps graph shape explicit.
        return s

    def node_codegen(s: State) -> State:
        emit({"type": "node_start", "node": "codegen"})
        out = run_codegen_stub(s, deps)
        emit({"type": "node_end", "node": "codegen"})
        return out

    def node_final(s: State) -> State:
        emit({"type": "node_start", "node": "final"})
        model, prompt = build_final_request(s, deps)
        answer = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)

        s["final"]["answer"] = answer

        emit({"type": "node_end", "node": "final"})
        emit({"type": "final", "answer": answer})
        return s

    # ----------------------
    # Conditional edge routers
    # ----------------------

    def route_after_router(s: State) -> str:
        return "retrieval" if _wants_retrieval(s, deps) else "codegen_gate"

    def route_after_codegen_gate(s: State) -> str:
        return "codegen" if _wants_codegen(s) else "final"

    # ----------------------
    # Graph build + invoke in worker thread
    # ----------------------

    def worker_thread() -> None:
        try:
            g: StateGraph = StateGraph(State)

            g.add_node("router", node_router)
            g.add_node("retrieval", node_retrieval)
            g.add_node("codegen_gate", node_codegen_gate)
            g.add_node("codegen", node_codegen)
            g.add_node("final", node_final)

            g.set_entry_point("router")

            # router -> retrieval? -> codegen_gate
            g.add_conditional_edges(
                "router",
                route_after_router,
                {
                    "retrieval": "retrieval",
                    "codegen_gate": "codegen_gate",
                },
            )

            # retrieval always goes to codegen_gate
            g.add_edge("retrieval", "codegen_gate")

            # codegen_gate -> codegen? -> final
            g.add_conditional_edges(
                "codegen_gate",
                route_after_codegen_gate,
                {
                    "codegen": "codegen",
                    "final": "final",
                },
            )

            # codegen always goes to final
            g.add_edge("codegen", "final")
            g.add_edge("final", END)

            compiled = g.compile()

            emit({"type": "log", "text": "\n[langgraph] compiled.invoke(state)\n"})
            _ = compiled.invoke(state)

        except Exception as e:
            emit({"type": "log", "text": f"\n[langgraph_runner] FAILED: {e}\n"})
        finally:
            q.put(None)

    t = threading.Thread(target=worker_thread, daemon=True)
    t.start()

    while True:
        ev = q.get()
        if ev is None:
            break
        yield ev
