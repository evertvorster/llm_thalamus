from __future__ import annotations

import json
from datetime import datetime, timezone

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.chat_messages_node import run_chat_messages_node
from orchestrator.nodes.episode_query_node import run_episode_query_node
from orchestrator.nodes.memory_retrieval_node import run_retrieval_node
from orchestrator.nodes.world_fetch_node import run_world_fetch_node
from orchestrator.state import State


def _extract_json_object(text: str) -> str:
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in executor output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    raise ValueError("unterminated JSON object in executor output")


def _next_attempt_id(state: State) -> int:
    attempts = state.get("runtime", {}).get("attempts", []) or []
    if not isinstance(attempts, list) or not attempts:
        return 1
    last = attempts[-1]
    if isinstance(last, dict):
        try:
            return int(last.get("attempt_id", 0)) + 1
        except Exception:
            return len(attempts) + 1
    return len(attempts) + 1


def _dispatch_step(state: State, deps: Deps, *, emit: callable | None) -> tuple[State, str]:
    """
    Mechanical execution of the selected step. Returns (new_state, observed_outcome_text).
    """
    step = state.get("runtime", {}).get("next_step", {}) or {}
    action = (step.get("action") or "").strip()
    args = step.get("args") if isinstance(step.get("args"), dict) else {}

    if action == "chat_messages":
        # Optionally allow overriding chat_history_k
        if "chat_history_k" in args:
            try:
                state["task"]["chat_history_k"] = int(args["chat_history_k"])
                state["task"]["need_chat_history"] = True
            except Exception:
                pass
        out = run_chat_messages_node(state, deps)
        n = len(out.get("context", {}).get("chat_history", []) or [])
        return out, f"chat_messages loaded turns={n}"

    if action == "memory_retrieval":
        if "retrieval_k" in args:
            try:
                state["task"]["retrieval_k"] = int(args["retrieval_k"])
            except Exception:
                pass
        out = run_retrieval_node(state, deps)
        mems = out.get("context", {}).get("memories", []) or []
        return out, f"memory_retrieval returned memories={len(mems)}"

    if action == "episode_query":
        out = run_episode_query_node(state, deps, emit=emit or (lambda _ev: None))
        summ = (out.get("context", {}).get("episodes_summary") or "").strip()
        hits = out.get("context", {}).get("episodes_hits", []) or []
        return out, f"episode_query summary_len={len(summ)} hits={len(hits)}"

    if action == "world_fetch_full":
        # Ensure full view for this fetch
        state["task"]["world_view"] = "full"
        out = run_world_fetch_node(state, deps)
        keys = sorted(list((out.get("world") or {}).keys()))
        return out, f"world_fetch_full merged keys={keys}"

    if action == "finalize":
        # Executor doesn't terminate; planner does. We just report.
        return state, "finalize requested (no-op in executor)"

    return state, f"unsupported action: {action!r}"


def run_executor_node(state: State, deps: Deps, *, emit: callable | None = None) -> State:
    if "tools" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.tools is required for executor node")

    step = state.get("runtime", {}).get("next_step", {}) or {}
    action = (step.get("action") or "").strip()
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    objective = (step.get("objective") or "").strip()
    success_criteria = (step.get("success_criteria") or "").strip()

    attempt_id = _next_attempt_id(state)
    step_id = (step.get("step_id") or action).strip() or action

    # Mechanical dispatch first (truth)
    observed_state, observed_outcome = _dispatch_step(state, deps, emit=emit)
    state = observed_state

    # Ask LLM to summarize and classify outcome for logs
    prompt = deps.prompt_loader.render(
        "executor",
        action=action,
        args=json.dumps(args, ensure_ascii=False),
        objective=objective,
        success_criteria=success_criteria,
        observed_outcome=observed_outcome,
    )

    raw = deps.llm_generate(deps.models["tools"], prompt).strip()
    try:
        blob = _extract_json_object(raw)
        data = json.loads(blob)
    except Exception:
        data = {}

    status = (data.get("status") or "").strip().lower()
    if status not in {"ok", "soft_fail", "hard_fail", "blocked"}:
        # Conservative default: if we got here without exception, treat as ok
        status = "ok"

    summary = (data.get("summary") or "").strip() or observed_outcome
    details = (data.get("details") or "").strip()
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []

    # Append attempt ledger entry
    state["runtime"]["attempts"].append(
        {
            "attempt_id": attempt_id,
            "step_id": step_id,
            "action": action,
            "args": args,
            "status": status,
            "summary": summary,
            "error": {},
            "artifacts": [],
            "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )

    # Append a human-friendly report
    state["runtime"]["reports"].append(
        {
            "node": "executor",
            "status": "ok" if status == "ok" else "warn",
            "summary": summary,
            "details": details,
            "related_attempt_ids": [attempt_id],
            "tags": ["executor"] + [str(t) for t in tags],
        }
    )

    return state
