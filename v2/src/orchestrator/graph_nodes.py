from __future__ import annotations

import json
from collections.abc import Callable

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.chat_messages_node import run_chat_messages_node
from orchestrator.nodes.codegen_node import run_codegen_stub
from orchestrator.nodes.episode_query_node import run_episode_query_node
from orchestrator.nodes.executor_node import run_executor_node
from orchestrator.nodes.final_node import build_final_request
from orchestrator.nodes.memory_retrieval_node import run_retrieval_node
from orchestrator.nodes.planner_node import run_planner_node
from orchestrator.nodes.router_node import build_router_request
from orchestrator.nodes.world_fetch_node import run_world_fetch_node
from orchestrator.state import State

_MAX_ROUTER_ROUNDS = 5


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


def _parse_router_output(raw: str) -> dict:
    """
    Router is a cheap gate. It returns ONLY:
      - route: "final" | "planner"
      - language: e.g. "en"
      - status: string (optional, may be empty)

    Anything else is ignored.
    """
    blob = _extract_json_object(raw)
    data = json.loads(blob)

    route = (data.get("route") or "").strip().lower()
    if route not in {"final", "planner"}:
        # Conservative default: planner (safer / more capable)
        route = "planner"

    language = (data.get("language") or "").strip().lower() or "en"

    status = data.get("status", "")
    if not isinstance(status, str):
        status = ""
    status = status.strip()

    return {"route": route, "language": language, "status": status}


def collect_streamed_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None],
) -> str:
    """
    IMPORTANT UI CONTRACT:
    Emit every streamed chunk as Event(type="log") so ControllerWorker forwards it to thinking_delta.
    """
    response_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue
        emit({"type": "log", "text": text})
        if kind == "response":
            response_parts.append(text)
    return "".join(response_parts).strip()


def make_dbg_chat(emit: Callable[[Event], None]) -> Callable[[str, State], None]:
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

    return _dbg_chat


# ---------------- node wrappers (State -> State) ----------------

def make_node_router(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    dbg_chat = make_dbg_chat(emit)

    def node_router(s: State) -> State:
        emit({"type": "node_start", "node": "router"})

        s["runtime"]["router_round"] = int(s["runtime"].get("router_round", 0)) + 1

        dbg_chat("before_router_prompt", s)
        model, prompt = build_router_request(s, deps)
        raw = collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)

        parsed = _parse_router_output(raw)

        # Router is now ONLY a gate:
        # - trivial => direct final
        # - non-trivial => planner/executor loop
        s["task"]["language"] = parsed["language"]
        s["runtime"]["status"] = parsed["status"]

        route = parsed["route"]
        s["task"]["plan_mode"] = "incremental" if route == "planner" else "direct"

        # Provide conservative defaults for the rest of the system.
        # (Planner will decide what to fetch; direct-mode will go to final.)
        s["task"].setdefault("intent", "qa")
        s["task"].setdefault("constraints", [])

        emit(
            {
                "type": "log",
                "text": (
                    "\n[route]"
                    f" round={s['runtime']['router_round']}/{_MAX_ROUTER_ROUNDS}"
                    f" route={route}"
                    f" plan_mode={s['task'].get('plan_mode')}"
                    f" status={'set' if bool((s.get('runtime', {}).get('status') or '').strip()) else 'empty'}"
                    f" language={s['task'].get('language')}"
                    "\n"
                ),
            }
        )

        emit({"type": "node_end", "node": "router"})
        return s

    return node_router


def make_node_chat_messages(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    dbg_chat = make_dbg_chat(emit)

    def node_chat_messages(s: State) -> State:
        emit({"type": "node_start", "node": "chat_messages"})
        out = run_chat_messages_node(s, deps)
        n = len(out.get("context", {}).get("chat_history", []) or [])
        emit({"type": "log", "text": f"\n[chat_messages] turns={n}\n"})
        dbg_chat("after_chat_messages_node", out)
        emit({"type": "node_end", "node": "chat_messages"})
        return out

    return node_chat_messages


def make_node_memory_retrieval(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_memory_retrieval(s: State) -> State:
        emit({"type": "node_start", "node": "memory_retrieval"})
        out = run_retrieval_node(s, deps)

        query = (out.get("context", {}) or {}).get("memory_retrieval", "")
        emit({"type": "log", "text": f"\n[memory_retrieval] query:\n{query}\n"})

        mems = out.get("context", {}).get("memories", []) or []
        emit({"type": "log", "text": f"\n[memory_retrieval] memories={len(mems)}\n"})

        # Top 3 hits in thinking log
        for i, m in enumerate(mems[:3], start=1):
            if not isinstance(m, dict):
                continue
            score = m.get("score")
            sector = m.get("sector")
            text = m.get("text", "")
            if not isinstance(text, str):
                text = str(text)
            preview = text[:200].replace("\n", "\\n")
            emit(
                {
                    "type": "log",
                    "text": f"[memory_retrieval] hit {i}: score={score} sector={sector} text={preview}\n",
                }
            )

        emit({"type": "node_end", "node": "memory_retrieval"})
        return out

    return node_memory_retrieval


def make_node_episode_query(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_episode_query(s: State) -> State:
        emit({"type": "node_start", "node": "episode_query"})
        out = run_episode_query_node(s, deps, emit=emit)

        summ = (out.get("context", {}).get("episodes_summary") or "").strip()
        hits = out.get("context", {}).get("episodes_hits", []) or []
        emit(
            {
                "type": "log",
                "text": (
                    f"\n[episode_query] summary_len={len(summ)} hits={len(hits)} "
                    f"status={(out.get('runtime', {}).get('status') or '').strip()!r}\n"
                ),
            }
        )
        emit({"type": "node_end", "node": "episode_query"})
        return out

    return node_episode_query


def make_node_world_prefetch(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_world_prefetch(s: State) -> State:
        """
        Pre-router world snapshot fetch.

        Under the router-as-gate approach, router does not depend on rich world state.
        We keep world_prefetch as-is (it is still useful elsewhere).
        """
        emit({"type": "node_start", "node": "world_prefetch"})
        out = run_world_fetch_node(s, deps)
        keys = sorted(list((out.get("world") or {}).keys()))
        emit({"type": "log", "text": f"\n[world_prefetch] keys={keys}\n"})
        emit({"type": "node_end", "node": "world_prefetch"})
        return out

    return node_world_prefetch


def make_node_world_fetch(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_world_fetch(s: State) -> State:
        emit({"type": "node_start", "node": "world_fetch"})
        out = run_world_fetch_node(s, deps)
        keys = sorted(list((out.get("world") or {}).keys()))
        emit({"type": "log", "text": f"\n[world_fetch] keys={keys}\n"})
        emit({"type": "node_end", "node": "world_fetch"})
        return out

    return node_world_fetch


def make_node_planner(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_planner(s: State) -> State:
        emit({"type": "node_start", "node": "planner"})
        out = run_planner_node(s, deps, emit=emit)
        term = (out.get("runtime", {}).get("termination") or {}).get("status", "")
        nxt = (out.get("runtime", {}).get("next_step") or {}).get("action", "")
        emit({"type": "log", "text": f"\n[planner] termination={term!r} next_action={nxt!r}\n"})
        emit({"type": "node_end", "node": "planner"})
        return out

    return node_planner


def make_node_executor(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_executor(s: State) -> State:
        emit({"type": "node_start", "node": "executor"})
        out = run_executor_node(s, deps, emit=emit)
        attempts = out.get("runtime", {}).get("attempts", []) or []
        last = attempts[-1] if isinstance(attempts, list) and attempts else {}
        emit({"type": "log", "text": f"\n[executor] last_attempt={last}\n"})
        emit({"type": "node_end", "node": "executor"})
        return out

    return node_executor


def make_node_back_to_router() -> Callable[[State], State]:
    def node_back_to_router(s: State) -> State:
        return s

    return node_back_to_router


def make_node_codegen_gate() -> Callable[[State], State]:
    def node_codegen_gate(s: State) -> State:
        return s

    return node_codegen_gate


def make_node_codegen(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    def node_codegen(s: State) -> State:
        emit({"type": "node_start", "node": "codegen"})
        out = run_codegen_stub(s, deps)
        emit({"type": "node_end", "node": "codegen"})
        return out

    return node_codegen


def make_node_final(deps: Deps, emit: Callable[[Event], None]) -> Callable[[State], State]:
    dbg_chat = make_dbg_chat(emit)

    def node_final(s: State) -> State:
        emit({"type": "node_start", "node": "final"})
        emit(
            {
                "type": "log",
                "text": f"\n[dbg_final] status={(s.get('runtime', {}).get('status') or '').strip()!r}\n",
            }
        )
        dbg_chat("before_final_prompt", s)
        model, prompt = build_final_request(s, deps)
        answer = collect_streamed_response(deps, model=model, prompt=prompt, emit=emit)
        s["final"]["answer"] = answer
        emit({"type": "node_end", "node": "final"})
        emit({"type": "final", "answer": answer})
        return s

    return node_final
