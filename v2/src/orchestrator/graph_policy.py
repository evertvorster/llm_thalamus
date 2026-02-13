from __future__ import annotations

from orchestrator.state import State

_MAX_ROUTER_ROUNDS = 5


def wants_chat(state: State) -> bool:
    t = state.get("task", {})
    if not bool(t.get("need_chat_history", False)):
        return False
    try:
        return int(t.get("chat_history_k", 0)) > 0
    except Exception:
        return False


def wants_retrieval(state: State) -> bool:
    try:
        return int(state["task"].get("retrieval_k", 0)) > 0
    except Exception:
        return False


def wants_episodes(state: State) -> bool:
    # Only run if router asked AND we don't already have an episodes summary.
    try:
        if not bool(state["task"].get("need_episodes", False)):
            return False
        summary = (state.get("context", {}).get("episodes_summary") or "").strip()
        return not bool(summary)
    except Exception:
        return False


def wants_world_fetch(state: State) -> bool:
    view = (state["task"].get("world_view") or "none").strip().lower()
    return view == "full"


def router_round_exceeded(state: State) -> bool:
    try:
        return int(state.get("runtime", {}).get("router_round", 0)) >= _MAX_ROUTER_ROUNDS
    except Exception:
        return True


def should_proceed_to_answer(state: State) -> bool:
    # If router has emitted a status message, go directly to final so it can clarify.
    try:
        if (state.get("runtime", {}).get("status") or "").strip():
            return True
    except Exception:
        pass

    if router_round_exceeded(state):
        return True

    ready = bool(state.get("task", {}).get("ready", True))
    if ready:
        return True

    if not (wants_chat(state) or wants_retrieval(state) or wants_episodes(state) or wants_world_fetch(state)):
        return True

    return False


def is_incremental_mode(state: State) -> bool:
    try:
        return (state.get("task", {}).get("plan_mode") or "direct").strip().lower() == "incremental"
    except Exception:
        return False


def planner_terminated(state: State) -> bool:
    term = (state.get("runtime", {}).get("termination") or {}).get("status")
    return bool(str(term or "").strip())


# -------- routing functions used by the graph --------

def route_after_router(state: State) -> str:
    # Router-as-gate: if plan_mode is incremental, always go to planner.
    if is_incremental_mode(state):
        return "planner"

    # Otherwise go to final (via codegen_gate which is currently a no-op)
    return "codegen_gate"


def route_after_planner(state: State) -> str:
    return "codegen_gate" if planner_terminated(state) else "executor"


def route_after_executor(state: State) -> str:
    return "planner"


def route_after_chat(state: State) -> str:
    if should_proceed_to_answer(state):
        return "codegen_gate"
    if wants_episodes(state):
        return "episode_query"
    if wants_retrieval(state):
        return "memory_retrieval"
    if wants_world_fetch(state):
        return "world_fetch"
    return "back_to_router"


def route_after_episode_query(state: State) -> str:
    if should_proceed_to_answer(state):
        return "codegen_gate"
    if wants_retrieval(state):
        return "memory_retrieval"
    if wants_world_fetch(state):
        return "world_fetch"
    return "back_to_router"


def route_after_memory_retrieval(state: State) -> str:
    if should_proceed_to_answer(state):
        return "codegen_gate"
    if wants_episodes(state):
        return "episode_query"
    if wants_world_fetch(state):
        return "world_fetch"
    return "back_to_router"


def route_after_world(state: State) -> str:
    if should_proceed_to_answer(state):
        return "codegen_gate"
    return "back_to_router"


def route_after_codegen_gate(state: State) -> str:
    # Codegen is out of scope for now.
    return "final"
