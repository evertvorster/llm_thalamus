from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)
_TZ_NAME = "Africa/Windhoek"


class Task(TypedDict):
    id: str
    user_input: str
    intent: str
    constraints: list[str]
    language: str

    # Router-controlled fetch plan
    need_chat_history: bool
    chat_history_k: int

    retrieval_k: int
    memory_query: str

    # Persistent world snapshot (time is always available by default; see State.world)
    world_view: str  # "none" | "full"

    # Router sets ready=true when it has enough context to proceed to answer/codegen.
    ready: bool


class Context(TypedDict):
    memories: list[dict]

    # chat tail loaded mechanically (for prompts / routing later)
    chat_history: list[dict]
    chat_history_text: str


class FinalOutput(TypedDict):
    answer: str


class Runtime(TypedDict):
    turn_seq: int
    node_trace: list[str]
    router_round: int

    # Router -> final status channel (empty string means "no status")
    status: str


class State(TypedDict):
    task: Task
    context: Context
    final: FinalOutput
    runtime: Runtime

    # Always present baseline keys:
    #   - now: ISO-8601 local time (Windhoek)
    #   - tz:  IANA timezone string
    #
    # If world_fetch runs with world_view="full", additional persistent keys
    # (topics/goals/project/updated_at/version) are merged into this dict.
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
            "world_view": "none",
            "ready": True,
        },
        "context": {
            "memories": [],
            "chat_history": [],
            "chat_history_text": "",
        },
        "final": {"answer": ""},
        "runtime": {
            "turn_seq": turn_seq,
            "node_trace": [],
            "router_round": 0,
            "status": "",
        },
        "world": {
            "now": now_iso,
            "tz": _TZ_NAME,
        },
    }
