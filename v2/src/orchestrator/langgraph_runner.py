from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Callable

from langgraph.graph import END, StateGraph

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.chat_messages_node import run_chat_messages_node
from orchestrator.nodes.codegen_node import run_codegen_stub
from orchestrator.nodes.final_node import build_final_request
from orchestrator.nodes.retrieval_node import run_retrieval_node
from orchestrator.nodes.router_node import build_router_request
from orchestrator.nodes.world_fetch_node import run_world_fetch_node
from orchestrator.state import State


_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}
_ALLOWED_WORLD_VIEWS = {"none", "time", "full"}


def _extract_json_object(text: str) -> str:
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


def _parse_router_output(raw: str, *, deps: Deps) -> dict:
    blob = _extract_json_object(raw)
    data = json.loads(blob)

    intent = (data.get("intent") or "").strip().lower()
    if intent not in _ALLOWED_INTENTS:
        intent = "qa"

    constraints = data.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []

    language = (data.get("language") or "").strip().lower() or "en"

    # Plan fields
    rk = data.get("retrieval_k", 0)
    try:
        rk = int(rk)
    except Exception:
        rk = 0

    max_k = int(deps.cfg.orchestrator_retrieval_max_k)
    if rk < 0:
        rk = 0
    if rk > max_k:
        rk = max_k

    world_view = (data.get("world_view") or "none").strip().lower()
    if world_view not in _ALLOWED_WORLD_VIEWS:
        world_view = "none"

    return {
        "intent": intent,
        "constraints": constraints,
        "language": language,
        "retrieval_k": rk,
        "world_view": world_view,
    }


def _collect_streamed_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None],
) -> str:
    response_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue
        emit({"type": "log", "text": text})
        if kind == "response":
            response_parts.append(text)
    return "".join(response_parts).strip()


def _wants_retrieval(state: State) -> bool:
    try:
        return int(state["task"].get("retrieval_k", 0)) > 0
    except Exception:
        return False


def _wants_world_fetch(state: State) -> bool:
    view = (state["task"].get("world_view") or "none").strip().lower()
    return view in {"time", "full"}


def _wants_codegen(state: State) -> bool:
    return state["task"]["intent"] == "coding"


def run_turn_langgraph(state: State, deps: Deps) -> Iterator[Event]:
    q: queue.Queue[Event | None] = queue.Queue()

    def emit(ev: Event) -> None:
        q.put(ev)

    def node_router(s: State) -> State:
        emit({"type": "node_start", "node": "router"})
        model, prompt = build_router_request(s, deps)
        raw = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)

        parsed = _parse_router_output(raw, deps=deps)
        s["task"]["intent"] = parsed["intent"]
        s["task"]["constraints"] = parsed["constraints"]
        s["task"]["language"] = parsed["language"]
        s["task"]["retrieval_k"] = parsed["retrieval_k"]
        s["task"]["world_view"] = parsed["world_view"]

        emit({"type": "log", "text": f"\n[plan] intent={s['task']['intent']} retrieval_k={s['task']['retrieval_k']} world_view={s['task']['world_view']}\n"})
        emit({"type": "node_end", "node": "router"})
        return s

    def node_chat_messages(s: State) -> State:
        emit({"type": "node_start", "node": "chat_messages"})
        out = run_chat_messages_node(s, deps)
        n = len(out.get("context", {}).get("chat_history", []) or [])
        emit({"type": "log", "text": f"\n[chat_messages] turns={n}\n"})
        emit({"type": "node_end", "node": "chat_messages"})
        return out

    def node_retrieval(s: State) -> State:
        emit({"type": "node_start", "node": "retrieval"})
        out = run_retrieval_node(s, deps)
        mems = out.get("context", {}).get("memories", []) or []
        emit({"type": "log", "text": f"\n[retrieval] memories={len(mems)}\n"})
        out["runtime"]["node_trace"].append("retrieval:openmemory")
        emit({"type": "node_end", "node": "retrieval"})
        return out

    def node_world_fetch(s: State) -> State:
        emit({"type": "node_start", "node": "world_fetch"})
        out = run_world_fetch_node(s, deps)
        emit({"type": "log", "text": f"\n[world_fetch] keys={sorted(list((out.get('world') or {}).keys()))}\n"})
        out["runtime"]["node_trace"].append(f"world_fetch:{s['task'].get('world_view')}")
        emit({"type": "node_end", "node": "world_fetch"})
        return out

    def node_codegen_gate(s: State) -> State:
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

    def route_after_chat_messages(s: State) -> str:
        # First branch: retrieval or skip
        return "retrieval" if _wants_retrieval(s) else "after_retrieval"

    def route_after_retrieval(s: State) -> str:
        # Second branch: world_fetch or skip
        return "world_fetch" if _wants_world_fetch(s) else "codegen_gate"

    def route_after_codegen_gate(s: State) -> str:
        return "codegen" if _wants_codegen(s) else "final"

    def worker_thread() -> None:
        try:
            g: StateGraph = StateGraph(State)

            g.add_node("router", node_router)
            g.add_node("chat_messages", node_chat_messages)
            g.add_node("retrieval", node_retrieval)

            # explicit junction nodes
            g.add_node("after_retrieval", lambda s: s)
            g.add_node("world_fetch", node_world_fetch)

            g.add_node("codegen_gate", node_codegen_gate)
            g.add_node("codegen", node_codegen)
            g.add_node("final", node_final)

            g.set_entry_point("router")

            # router always leads to chat_messages (mechanical tail read)
            g.add_edge("router", "chat_messages")

            g.add_conditional_edges(
                "chat_messages",
                route_after_chat_messages,
                {
                    "retrieval": "retrieval",
                    "after_retrieval": "after_retrieval",
                },
            )
            g.add_edge("retrieval", "after_retrieval")

            g.add_conditional_edges(
                "after_retrieval",
                route_after_retrieval,
                {
                    "world_fetch": "world_fetch",
                    "codegen_gate": "codegen_gate",
                },
            )
            g.add_edge("world_fetch", "codegen_gate")

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

            compiled = g.compile()
            emit({"type": "log", "text": "\n[langgraph] compiled.invoke(state)\n"})
            _ = compiled.invoke(state)

        except Exception as e:
            emit({"type": "log", "text": f"\n[langgraph_runner] FAILED: {e}\n"})
        finally:
            q.put(None)

    threading.Thread(target=worker_thread, daemon=True).start()

    while True:
        ev = q.get()
        if ev is None:
            break
        yield ev
