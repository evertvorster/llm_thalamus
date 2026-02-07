from __future__ import annotations

from typing import Literal, TypedDict


class Task(TypedDict):
    id: str
    user_input: str
    intent: str
    constraints: list[str]
    language: str
    retrieval_k: int | None


class Context(TypedDict):
    memories: list[dict]


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
    # Read-only snapshot of persistent world state + derived per-run facts.
    # For now, controller injects this (can be {}).
    world: dict


def new_state_for_turn(
    *,
    turn_id: str,
    user_input: str,
    turn_seq: int,
    world: dict | None = None,
) -> State:
    return {
        "task": {
            "id": turn_id,
            "user_input": user_input,
            "intent": "",
            "constraints": [],
            "language": "",
            "retrieval_k": None,
        },
        "context": {
            "memories": [],
        },
        "final": {"answer": ""},
        "runtime": {"turn_seq": turn_seq, "node_trace": []},
        "world": dict(world or {}),
    }
