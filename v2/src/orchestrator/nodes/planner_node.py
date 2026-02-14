from __future__ import annotations

import json
from collections.abc import Callable

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.state import State

_ALLOWED_ACTIONS = {
    "chat_messages",
    "memory_retrieval",
    "episode_query",
    "world_fetch_full",
    "finalize",
}

_MAX_PLANNER_ROUNDS_DEFAULT = 12


def _collect_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None] | None = None,
) -> str:
    """
    Collect the streamed response into a single string.

    UI contract (when emit is provided):
      - forward every streamed chunk as Event(type="log") so the UI receives "thinking" deltas
      - do not tag or prefix text; keep output raw/unchanged
    """
    response_parts: list[str] = []
    for kind, chunk in deps.llm_generate_stream(model, prompt):
        if not chunk:
            continue
        if emit is not None:
            emit({"type": "log", "text": chunk})
        if kind == "response":
            response_parts.append(chunk)
    return "".join(response_parts).strip()


def _extract_json_object(text: str) -> str:
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in planner output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    raise ValueError("unterminated JSON object in planner output")


def _world_summary(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return "(empty)"
    keys = ["now", "tz", "project", "updated_at", "topics", "goals"]
    lines: list[str] = []
    for k in keys:
        if k in w:
            lines.append(f"{k}: {w.get(k)}")
    return "\n".join(lines) if lines else "(empty)"


def _attempts_summary(state: State, *, max_items: int = 12) -> str:
    attempts = state.get("runtime", {}).get("attempts", []) or []
    if not isinstance(attempts, list) or not attempts:
        return "(none)"
    lines: list[str] = []
    for a in attempts[-max_items:]:
        if not isinstance(a, dict):
            continue
        aid = a.get("attempt_id")
        action = a.get("action")
        status = a.get("status")
        summary = (a.get("summary") or "").strip()
        summary = summary.replace("\n", "\\n")[:220]
        lines.append(f"- attempt={aid} action={action} status={status} summary={summary}")
    return "\n".join(lines) if lines else "(none)"


def _context_status(state: State) -> dict[str, str]:
    ctx = state.get("context") or {}
    chat_text = str(ctx.get("chat_history_text") or "").strip()
    mems = ctx.get("memories", []) or []
    eps = str(ctx.get("episodes_summary") or "").strip()

    w = state.get("world") or {}
    world_full_present = all(k in w for k in ("project", "topics", "goals", "rules", "identity", "updated_at"))

    return {
        "chat_present": "true" if bool(chat_text) else "false",
        "memories_count": str(len(mems) if isinstance(mems, list) else 0),
        "episodes_present": "true" if bool(eps) else "false",
        "world_full_present": "true" if bool(world_full_present) else "false",
    }

def _context_block(state: State, *, max_chars: int = 8000) -> str:
    """
    JSON dump of state['context'] for planner visibility (truncated).
    Keep this simple: planner can see what we already fetched.
    """
    ctx = state.get("context") or {}
    try:
        s = json.dumps(ctx, ensure_ascii=False, indent=2)
    except Exception:
        s = str(ctx)

    if len(s) > max_chars:
        return s[:max_chars] + "\n... (truncated)"
    return s



def run_planner_node(state: State, deps: Deps, *, emit: Callable[[Event], None] | None = None) -> State:
    if "planner" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.planner is required for planner node")

    # Increment planner round counter (append-only behavior elsewhere)
    rt = state.get("runtime") or {}
    state["runtime"]["planner_round"] = int(rt.get("planner_round", 0) or 0) + 1

    max_rounds = int(getattr(deps.cfg, "orchestrator_planner_max_rounds", _MAX_PLANNER_ROUNDS_DEFAULT))
    if state["runtime"]["planner_round"] > max_rounds:
        state["runtime"]["termination"] = {
            "status": "failed",
            "reason": f"planner exceeded max rounds ({max_rounds})",
            "needs_user": "",
        }
        state["runtime"]["reports"].append(
            {
                "node": "planner",
                "status": "error",
                "summary": f"Terminating: exceeded max planner rounds ({max_rounds}).",
                "tags": ["planner", "termination"],
            }
        )
        return state

    t = state.get("task") or {}
    ctx_status = _context_status(state)

    # NEW: provide planner with actual chat turn count
    ctx = state.get("context") or {}
    chat_turns_count = len(ctx.get("chat_history") or [])

    prompt = deps.prompt_loader.render(
        "planner",
        user_input=state["task"]["user_input"],
        intent=str(t.get("intent") or ""),
        constraints=str(t.get("constraints") or []),
        language=str(t.get("language") or "en"),
        world_summary=_world_summary(state),
        attempts_summary=_attempts_summary(state),
        chat_turns_count=chat_turns_count,
        context_block=_context_block(state),
        **ctx_status,
    )


    raw = _collect_response(deps, model=deps.models["planner"], prompt=prompt, emit=emit)
    blob = _extract_json_object(raw)
    data = json.loads(blob)

    # Handle termination
    term = data.get("termination")
    if isinstance(term, dict):
        status = (term.get("status") or "").strip().lower()
        if status not in {"done", "blocked", "failed", "aborted"}:
            status = "failed"
        reason = (term.get("reason") or "").strip() or "terminated"
        needs_user = (term.get("needs_user") or "").strip()

        state["runtime"]["termination"] = {
            "status": status,
            "reason": reason,
            "needs_user": needs_user,
        }
        state["runtime"]["reports"].append(
            {
                "node": "planner",
                "status": "ok" if status == "done" else "warn",
                "summary": f"Termination selected: {status}. Reason: {reason}",
                "details": needs_user if needs_user else "",
                "tags": ["planner", "termination"],
            }
        )
        return state

    # Handle next_step
    ns = data.get("next_step")
    if not isinstance(ns, dict):
        state["runtime"]["termination"] = {
            "status": "failed",
            "reason": "planner returned neither next_step nor termination",
            "needs_user": "",
        }
        state["runtime"]["reports"].append(
            {
                "node": "planner",
                "status": "error",
                "summary": "Planner output invalid (no next_step/termination).",
                "tags": ["planner", "parse"],
            }
        )
        return state

    action = (ns.get("action") or "").strip()
    if action not in _ALLOWED_ACTIONS:
        state["runtime"]["termination"] = {
            "status": "failed",
            "reason": f"planner returned unsupported action: {action!r}",
            "needs_user": "",
        }
        state["runtime"]["reports"].append(
            {
                "node": "planner",
                "status": "error",
                "summary": f"Planner chose unsupported action: {action!r}.",
                "tags": ["planner", "action"],
            }
        )
        return state

    # Normalize step fields
    step_id = (ns.get("step_id") or action).strip() or action
    args = ns.get("args") if isinstance(ns.get("args"), dict) else {}
    objective = (ns.get("objective") or "").strip()
    success_criteria = (ns.get("success_criteria") or "").strip()
    output_contract = (ns.get("output_contract") or "").strip()

    state["runtime"]["next_step"] = {
        "step_id": step_id,
        "action": action,
        "args": args,
        "objective": objective,
        "success_criteria": success_criteria,
        "output_contract": output_contract,
    }

    state["runtime"]["reports"].append(
        {
            "node": "planner",
            "status": "ok",
            "summary": f"Next step: action={action} step_id={step_id}",
            "details": objective,
            "tags": ["planner", "next_step"],
        }
    )
    return state
