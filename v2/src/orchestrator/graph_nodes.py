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

_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}
_ALLOWED_WORLD_VIEWS = {"none", "summary", "full"}

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

    # episodic retrieval
    need_episodes = bool(data.get("need_episodes", False))

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
        "need_episodes": need_episodes,
        "world_view": world_view,
    }


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

        parsed = _parse_router_output(raw, deps=deps)
        s["task"]["intent"] = parsed["intent"]
        s["task"]["constraints"] = parsed["constraints"]
        s["task"]["language"] = parsed["language"]

        s["task"]["ready"] = parsed["ready"]
        s["task"]["need_chat_history"] = parsed["need_chat_history"]
        s["task"]["chat_history_k"] = parsed["chat_history_k"]

        s["task"]["retrieval_k"] = parsed["retrieval_k"]
        s["task"]["need_episodes"] = parsed["need_episodes"]
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
                    f" memory_retrieval_k={s['task']['retrieval_k']}"
                    f" need_episodes={bool(s['task'].get('need_episodes', False))}"
                    f" world_view={s['task']['world_view']}"
                    f" plan_mode={(s.get('task', {}).get('plan_mode') or 'direct')}"
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
        out = run_planner_node(s, deps)
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
