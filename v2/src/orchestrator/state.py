from __future__ import annotations

from typing import TypedDict


class Task(TypedDict):
    id: str
    user_input: str
    intent: str
    constraints: list[str]
    language: str

    # Router-controlled fetch plan
    retrieval_k: int
    world_view: str  # "none" | "time" | "full"


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


class State(TypedDict):
    task: Task
    context: Context
    final: FinalOutput
    runtime: Runtime

    # Populated ONLY if world_fetch node ran.
    # This is the "payload view" that downstream nodes can render into prompts.
    world: dict


def new_state_for_turn(
    *,
    turn_id: str,
    user_input: str,
    turn_seq: int,
) -> State:
    return {
        "task": {
            "id": turn_id,
            "user_input": user_input,
            "intent": "",
            "constraints": [],
            "language": "en",
            # Router decides these; defaults are safe "no fetch"
            "retrieval_k": 0,
            "world_view": "none",
        },
        "context": {
            "memories": [],
            "chat_history": [],
            "chat_history_text": "",
        },
        "final": {"answer": ""},
        "runtime": {"turn_seq": turn_seq, "node_trace": []},
        "world": {},
    }
