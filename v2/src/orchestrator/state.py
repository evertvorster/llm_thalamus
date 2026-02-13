from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)
_TZ_NAME = "Africa/Windhoek"


# ----------------------------
# Planner/Executor primitives
# ----------------------------

class StepSpec(TypedDict, total=False):
    """
    A single incremental step selected by the planner and executed mechanically.

    This is intentionally small and flexible:
    - The planner decides 'action' + 'args'
    - The executor/tool normalizes outputs into runtime.attempts + runtime.reports

    NOTE: Many nodes may exist in future. We keep StepSpec generic and tool-driven.
    """
    step_id: str              # Logical step id (retries share a step_id)
    action: str               # e.g. "openmemory.search", "episodic.query", "mcp.fs.read"
    args: dict                # Typed per action/tool domain (kept generic here)
    objective: str            # Natural language instruction ("what to do")
    success_criteria: str     # Natural language ("what success looks like")
    output_contract: str      # Natural language or mini-schema guidance for the worker
    relevant_attempt_ids: list[int]  # Optional: attempts relevant to this step


class Attempt(TypedDict, total=False):
    """
    Append-only execution attempt record.

    Ground truth of "what was tried", used by planner to decide whether to retry/fallback/ask user.
    """
    attempt_id: int
    step_id: str
    action: str
    args: dict
    status: str               # "ok" | "soft_fail" | "hard_fail" | "blocked"
    summary: str              # Natural language short summary of outcome
    error: dict               # {"code": str|None, "message": str, "details": str|None}
    artifacts: list[dict]     # Optional outputs (paths/ids/etc.)
    ts_utc: str


class NodeReport(TypedDict, total=False):
    """
    Natural-language inter-node communication envelope.

    Nodes append reports so later nodes (planner/final) can reason over what happened.
    """
    node: str                 # "router" | "planner" | "executor" | "final" | "reflect" | ...
    status: str               # "ok" | "warn" | "error"
    summary: str              # 1-10 lines
    details: str              # Optional longer text
    related_attempt_ids: list[int]
    tags: list[str]


class Termination(TypedDict, total=False):
    """
    Planner-controlled termination decision for the incremental loop.
    """
    status: str               # "done" | "blocked" | "failed" | "aborted"
    reason: str               # Natural language one-liner
    needs_user: str           # If blocked, the question/instruction for the user


# ----------------------------
# Core State (existing shape)
# ----------------------------

class Task(TypedDict):
    id: str
    user_input: str
    intent: str
    constraints: list[str]
    language: str

    # Router-controlled fetch plan (legacy: still used by current working graph)
    need_chat_history: bool
    chat_history_k: int

    retrieval_k: int
    memory_query: str

    # Episodic retrieval
    need_episodes: bool

    # Persistent world snapshot (time is always available by default; see State.world)
    # - "none":    do not fetch or display persistent world state
    # - "summary": fetch a small subset (project/topics/updated_at)
    # - "full":    fetch the full snapshot (project/topics/goals/rules/identity/updated_at)
    world_view: str  # "none" | "summary" | "full"

    # Router sets ready=true when it has enough context to proceed to answer/codegen.
    # NOTE: With incremental planner/executor, "ready" means "safe to proceed into planning loop".
    ready: bool

    # NEW: planning mode knob (kept on Task so it's always available early)
    # - "direct":      current behavior (router gathers context, final answers)
    # - "incremental": future behavior (planner/executor loop)
    plan_mode: str  # "direct" | "incremental"


class Context(TypedDict):
    memories: list[dict]

    # Chat tail loaded mechanically (for prompts / routing later)
    chat_history: list[dict]
    chat_history_text: str

    # Episodic retrieval outputs (ephemeral only)
    episodes_summary: str
    episodes_hits: list[dict]


class FinalOutput(TypedDict):
    answer: str


class Runtime(TypedDict):
    turn_seq: int
    node_trace: list[str]

    # Legacy counter used in the current working graph
    router_round: int

    # Router -> final status channel (empty string means "no status")
    status: str

    # Reflection summary written by reflect/store for downstream mechanical logging.
    # (episodic database, probes, etc.)
    reflection: dict

    # ----------------------------
    # NEW: Incremental planning loop
    # ----------------------------

    # Planner/executor iteration counter (separate from router_round)
    planner_round: int

    # Next step to run (selected by planner, executed by executor)
    next_step: StepSpec

    # Append-only attempt ledger and node reports
    attempts: list[Attempt]
    reports: list[NodeReport]

    # If set, planner has terminated the loop (done/blocked/failed/aborted)
    termination: Termination


class State(TypedDict):
    task: Task
    context: Context
    final: FinalOutput
    runtime: Runtime

    # Always present baseline keys:
    #   - now: ISO-8601 local time (Windhoek)
    #   - tz:  IANA timezone string
    #
    # If world_fetch runs with world_view="summary" or "full", additional persistent keys
    # are merged into this dict.
    world: dict


def new_state_for_turn(
    *,
    turn_id: str,
    user_input: str,
    turn_seq: int,
) -> State:
    now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")

    return {
        "task": {
            "id": turn_id,
            "user_input": user_input,
            "intent": "",
            "constraints": [],
            "language": "en",
            "need_chat_history": False,
            "chat_history_k": 0,
            "retrieval_k": 0,
            "memory_query": "",
            "need_episodes": False,
            # Default: give router a small persistent world snapshot on first pass.
            "world_view": "summary",
            "ready": True,
            # Default: preserve current behavior until planner/executor is wired.
            "plan_mode": "direct",
        },
        "context": {
            "memories": [],
            "chat_history": [],
            "chat_history_text": "",
            "episodes_summary": "",
            "episodes_hits": [],
        },
        "final": {"answer": ""},
        "runtime": {
            "turn_seq": turn_seq,
            "node_trace": [],
            "router_round": 0,
            "status": "",
            "reflection": {},
            # Incremental planning loop fields (safe defaults)
            "planner_round": 0,
            "next_step": {},
            "attempts": [],
            "reports": [],
            "termination": {},
        },
        "world": {
            "now": now_iso,
            "tz": _TZ_NAME,
        },
    }
