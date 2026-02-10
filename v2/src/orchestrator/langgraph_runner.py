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

_MAX_ROUTER_ROUNDS = 5

_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}
_ALLOWED_WORLD_VIEWS = {"none", "summary", "full"}


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

    ready = bool(data.get("ready", True))

    # Router -> final status channel (empty string means "no status")
    status = data.get("status", "")
    if not isinstance(status, str):
        status = ""
    status = status.strip()

    need_chat_history = bool(data.get("need_chat_history", False))
    chat_history_k = data.get("chat_history_k", 0)
    try:
        chat_history_k = int(chat_history_k)
    except Exception:
        chat_history_k = 0
    if chat_history_k < 0:
        chat_history_k = 0
    if chat_history_k > 50:
        chat_history_k = 50

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

    memory_query = data.get("memory_query", "")
    if not isinstance(memory_query, str):
        memory_query = ""
    memory_query = memory_query.strip()

    world_view = (data.get("world_view") or "summary").strip().lower()
    if world_view not in _ALLOWED_WORLD_VIEWS:
        world_view = "summary"

    return {
        "intent": intent,
        "constraints": constraints,
        "language": language,
        "ready": ready,
        "status": status,
        "need_chat_history": need_chat_history,
        "chat_history_k": chat_history_k,
        "retrieval_k": rk,
        "memory_query": memory_query,
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


def _wants_chat(state: State) -> bool:
    t = state.get("task", {})
    if not bool(t.get("need_chat_history", False)):
        return False
    try:
        return int(t.get("chat_history_k", 0)) > 0
    except Exception:
        return False


def _wants_retrieval(state: State) -> bool:
    try:
        return int(state["task"].get("retrieval_k", 0)) > 0
    except Exception:
        return False


def _wants_world_fetch(state: State) -> bool:
    view = (state["task"].get("world_view") or "none").strip().lower()
    return view == "full"


def _wants_codegen(state: State) -> bool:
    return state["task"]["intent"] == "coding"


def _router_round_exceeded(state: State) -> bool:
    try:
        return int(state.get("runtime", {}).get("router_round", 0)) >= _MAX_ROUTER_ROUNDS
    except Exception:
        return True


def _should_proceed_to_answer(state: State) -> bool:
    # If router has emitted a status message, go directly to final so it can clarify.
    try:
        if (state.get("runtime", {}).get("status") or "").strip():
            return True
    except Exception:
        pass

    if _router_round_exceeded(state):
        return True

    ready = bool(state.get("task", {}).get("ready", True))
    if ready:
        return True

    if not (_wants_chat(state) or _wants_retrieval(state) or _wants_world_fetch(state)):
        return True

    return False


def run_turn_langgraph(state: State, deps: Deps) -> Iterator[Event]:
    q: queue.Queue[Event | None] = queue.Queue()

    def emit(ev: Event) -> None:
        q.put(ev)

    def _dbg_chat(stage: str, s: State) -> None:
        """Instrumentation-only: log whether chat_history_text exists and what it contains."""
        try:
            ctx = s.get("context", {}) or {}
            turns = len(ctx.get("chat_history", []) or [])
            text = ctx.get("chat_history_text", "") or ""
            if not isinstance(text, str):
                text = str(text)
            preview = text[:200].replace("\n", "\\n")
            emit(
                {
                    "type": "log",
                    "text": (
                        f"\n[dbg_chat:{stage}] turns={turns} len={len(text)} "
                        f"preview={preview!r}\n"
                    ),
                }
            )
        except Exception as e:
            emit({"type": "log", "text": f"\n[dbg_chat:{stage}] FAILED: {e}\n"})

    def node_router(s: State) -> State:
        emit({"type": "node_start", "node": "router"})

        s["runtime"]["router_round"] = int(s["runtime"].get("router_round", 0)) + 1

        _dbg_chat("before_router_prompt", s)
        model, prompt = build_router_request(s, deps)
        raw = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)

        parsed = _parse_router_output(raw, deps=deps)
        s["task"]["intent"] = parsed["intent"]
        s["task"]["constraints"] = parsed["constraints"]
        s["task"]["language"] = parsed["language"]

        s["task"]["ready"] = parsed["ready"]
        s["task"]["need_chat_history"] = parsed["need_chat_history"]
        s["task"]["chat_history_k"] = parsed["chat_history_k"]

        s["task"]["retrieval_k"] = parsed["retrieval_k"]
        s["task"]["memory_query"] = parsed["memory_query"]
        s["task"]["world_view"] = parsed["world_view"]

        # Persist router->final status (one-string channel).
        s["runtime"]["status"] = parsed["status"]

        # If router emitted status, stop requesting chat in a loop.
        if s["runtime"]["status"]:
            s["task"]["need_chat_history"] = False
            s["task"]["chat_history_k"] = 0

        emit(
            {
                "type": "log",
                "text": (
                    "\n[plan]"
                    f" round={s['runtime']['router_round']}/{_MAX_ROUTER_ROUNDS}"
                    f" intent={s['task']['intent']}"
                    f" ready={s['task']['ready']}"
                    f" status={'set' if bool((s.get('runtime', {}).get('status') or '').strip()) else 'empty'}"
                    f" chat={s['task']['need_chat_history']}/{s['task']['chat_history_k']}"
                    f" retrieval_k={s['task']['retrieval_k']}"
                    f" world_view={s['task']['world_view']}"
                    "\n"
                ),
            }
        )
        emit({"type": "node_end", "node": "router"})
        return s

    def node_chat_messages(s: State) -> State:
        emit({"type": "node_start", "node": "chat_messages"})
        out = run_chat_messages_node(s, deps)
        n = len(out.get("context", {}).get("chat_history", []) or [])
        emit({"type": "log", "text": f"\n[chat_messages] turns={n}\n"})
        _dbg_chat("after_chat_messages_node", out)
        emit({"type": "node_end", "node": "chat_messages"})
        return out

    def node_retrieval(s: State) -> State:
        emit({"type": "node_start", "node": "retrieval"})
        out = run_retrieval_node(s, deps)
        mems = out.get("context", {}).get("memories", []) or []
        emit({"type": "log", "text": f"\n[retrieval] memories={len(mems)}\n"})
        emit({"type": "node_end", "node": "retrieval"})
        return out

    def node_world_prefetch(s: State) -> State:
        """
        Pre-router world snapshot fetch.

        By default, state.task.world_view starts as "summary" (see new_state_for_turn),
        which means the router gets a small persistent world context on its first pass.
        If world_view is "none", this becomes a no-op.
        """
        emit({"type": "node_start", "node": "world_prefetch"})
        out = run_world_fetch_node(s, deps)
        keys = sorted(list((out.get("world") or {}).keys()))
        emit({"type": "log", "text": f"\n[world_prefetch] keys={keys}\n"})
        emit({"type": "node_end", "node": "world_prefetch"})
        return out

    def node_world_fetch(s: State) -> State:
        emit({"type": "node_start", "node": "world_fetch"})
        out = run_world_fetch_node(s, deps)
        keys = sorted(list((out.get("world") or {}).keys()))
        emit({"type": "log", "text": f"\n[world_fetch] keys={keys}\n"})
        emit({"type": "node_end", "node": "world_fetch"})
        return out

    def node_back_to_router(s: State) -> State:
        return s

    def node_codegen_gate(s: State) -> State:
        return s

    def node_codegen(s: State) -> State:
        emit({"type": "node_start", "node": "codegen"})
        out = run_codegen_stub(s, deps)
        emit({"type": "node_end", "node": "codegen"})
        return out

    def node_final(s: State) -> State:
        emit({"type": "node_start", "node": "final"})
        emit({"type": "log", "text": f"\n[dbg_final] status={(s.get('runtime', {}).get('status') or '').strip()!r}\n"})
        _dbg_chat("before_final_prompt", s)
        model, prompt = build_final_request(s, deps)
        answer = _collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)
        s["final"]["answer"] = answer
        emit({"type": "node_end", "node": "final"})
        emit({"type": "final", "answer": answer})
        return s

    def route_after_router(s: State) -> str:
        if _should_proceed_to_answer(s):
            return "codegen_gate"

        if _wants_chat(s):
            return "chat_messages"
        if _wants_retrieval(s):
            return "retrieval"
        if _wants_world_fetch(s):
            return "world_fetch"
        return "codegen_gate"

    def route_after_chat(s: State) -> str:
        if _should_proceed_to_answer(s):
            return "codegen_gate"
        if _wants_retrieval(s):
            return "retrieval"
        if _wants_world_fetch(s):
            return "world_fetch"
        return "back_to_router"

    def route_after_retrieval(s: State) -> str:
        if _should_proceed_to_answer(s):
            return "codegen_gate"
        if _wants_world_fetch(s):
            return "world_fetch"
        return "back_to_router"

    def route_after_world(s: State) -> str:
        if _should_proceed_to_answer(s):
            return "codegen_gate"
        return "back_to_router"

    def route_after_codegen_gate(s: State) -> str:
        return "codegen" if _wants_codegen(s) else "final"

    def worker_thread() -> None:
        try:
            g: StateGraph = StateGraph(State)

            g.add_node("world_prefetch", node_world_prefetch)
            g.add_node("router", node_router)
            g.add_node("chat_messages", node_chat_messages)
            g.add_node("retrieval", node_retrieval)
            g.add_node("world_fetch", node_world_fetch)
            g.add_node("back_to_router", node_back_to_router)

            g.add_node("codegen_gate", node_codegen_gate)
            g.add_node("codegen", node_codegen)
            g.add_node("final", node_final)

            # Pre-router default: fetch a small persistent world snapshot (summary)
            # so router has grounding context without paying full "world_view=full" cost.
            g.set_entry_point("world_prefetch")
            g.add_edge("world_prefetch", "router")

            g.add_conditional_edges(
                "router",
                route_after_router,
                {
                    "chat_messages": "chat_messages",
                    "retrieval": "retrieval",
                    "world_fetch": "world_fetch",
                    "codegen_gate": "codegen_gate",
                },
            )

            g.add_conditional_edges(
                "chat_messages",
                route_after_chat,
                {
                    "retrieval": "retrieval",
                    "world_fetch": "world_fetch",
                    "back_to_router": "back_to_router",
                    "codegen_gate": "codegen_gate",
                },
            )

            g.add_conditional_edges(
                "retrieval",
                route_after_retrieval,
                {
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
