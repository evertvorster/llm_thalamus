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

        # Forward both thinking + response for UI visibility (same as runner_seq)
        emit({"type": "log", "text": text})

        if kind == "response":
            response_parts.append(text)

    return "".join(response_parts).strip()


def _wants_retrieval(state: State, deps: Deps) -> bool:
    """
    Keep the *current* retrieval policy:
      - Always run for research/ops
      - Also run for any intent if default_k > 0
    """
    intent = state["task"]["intent"]
    default_k = int(deps.cfg.orchestrator_retrieval_default_k)
    return (intent in {"research", "ops"}) or (default_k > 0)


def _wants_codegen(state: State) -> bool:
    return state["task"]["intent"] == "coding"


def build_graph() -> StateGraph:
    """
    Build the single long-lived graph:
      router -> (retrieval?) -> (codegen?) -> final -> END
    Reflection/store remains post-graph in ControllerWorker by design.
    """
    g: StateGraph = StateGraph(State)

    # Node names intentionally match your current event names.
    g.add_node("router", lambda s: s)
    g.add_node("retrieval", lambda s: s)
    g.add_node("codegen", lambda s: s)
    g.add_node("final", lambda s: s)

    g.set_entry_point("router")

    # router -> retrieval? -> maybe codegen -> final
    g.add_conditional_edges(
        "router",
        lambda s: "retrieval" if _wants_retrieval(s, g._deps) else "maybe_codegen",  # type: ignore[attr-defined]
        {
            "retrieval": "retrieval",
            "maybe_codegen": "codegen_gate",
        },
    )

    # We route through an explicit “gate” node name by using conditional edges on retrieval/codegen.
    # However, LangGraph edges require actual nodes; we model the gate by conditional edges directly:
    #
    # retrieval -> codegen? -> final
    g.add_conditional_edges(
        "retrieval",
        lambda s: "codegen" if _wants_codegen(s) else "final",
        {"codegen": "codegen", "final": "final"},
    )

    # router-skip path: router -> codegen? -> final
    g.add_conditional_edges(
        "codegen",  # this is okay; codegen may be reached from router-skip or retrieval
        lambda s: "final",
        {"final": "final"},
    )
    # If codegen is skipped, we need router-skip to go directly to final.
    # We model this by allowing router to go to "codegen" node and then it will no-op if not coding,
    # but we prefer explicit. Instead, we do:
    #
    # router-skip -> final directly (handled via "codegen_gate" alias in runtime wrapper)
    #
    # Since StateGraph requires actual nodes, we won't create "codegen_gate" as a node.
    # We'll implement routing in the runtime runner below (keeping this graph minimal and stable).

    g.add_edge("final", END)
    return g


def run_turn_langgraph(state: State, deps: Deps) -> Iterator[Event]:
    """
    Execute the LangGraph graph while preserving your existing streaming Event protocol.

    Implementation detail:
      - We run graph execution in a background thread.
      - Node wrappers emit events into a queue (node_start/log/node_end/final).
      - This generator yields events live to the caller (ControllerWorker).

    Reflection is *not* part of the graph by explicit project rule.
    """
    q: queue.Queue[Event | None] = queue.Queue()

    def emit(ev: Event) -> None:
        q.put(ev)

    def run_router(s: State) -> State:
        emit({"type": "node_start", "node": "router"})
        model, prompt = build_router_request(s, deps)
        raw = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)
        emit({"type": "node_end", "node": "router"})

        parsed = _parse_router_output(raw)
        s["task"]["intent"] = parsed["intent"]
        s["task"]["constraints"] = parsed["constraints"]
        s["task"]["language"] = parsed["language"]
        return s

    def run_retrieval(s: State) -> State:
        # caller can override; None means "use config default"
        s["task"]["retrieval_k"] = None

        emit({"type": "node_start", "node": "retrieval"})
        out = run_retrieval_node(s, deps)

        mems = out.get("context", {}).get("memories", []) or []
        emit({"type": "log", "text": f"\n[retrieval] memories={len(mems)}\n"})
        for m in mems[:3]:
            txt = str(m.get("text", "") or "")
            emit({"type": "log", "text": f"- {txt[:200]}\n"})

        out["runtime"]["node_trace"].append("retrieval:openmemory")
        emit({"type": "node_end", "node": "retrieval"})
        return out

    def run_codegen(s: State) -> State:
        emit({"type": "node_start", "node": "codegen"})
        out = run_codegen_stub(s, deps)
        emit({"type": "node_end", "node": "codegen"})
        return out

    def run_final(s: State) -> State:
        emit({"type": "node_start", "node": "final"})
        model, prompt = build_final_request(s, deps)
        answer = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)
        emit({"type": "node_end", "node": "final"})

        s["final"]["answer"] = answer
        emit({"type": "final", "answer": answer})
        return s

    def worker_thread() -> None:
        """
        We keep LangGraph as the structural definition, but we execute the same
        node order with explicit conditional gating so we can preserve live streaming.
        """
        try:
            # 1) router (always)
            s = run_router(state)

            # 2) retrieval (optional)
            if _wants_retrieval(s, deps):
                s = run_retrieval(s)

            # 3) codegen (optional)
            if _wants_codegen(s):
                s = run_codegen(s)
            else:
                # keep trace behavior compatible with runner_seq planning fallthrough
                if s["task"]["intent"] == "planning":
                    s["runtime"]["node_trace"].append("planning:fallthrough")

            # 4) final (always)
            _ = run_final(s)

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
