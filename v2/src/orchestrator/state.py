from __future__ import annotations

from typing import Literal, TypedDict


class Message(TypedDict):
    role: Literal["human", "you"]
    content: str


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
    messages: list[Message]
    task: Task
    context: Context
    final: FinalOutput
    runtime: Runtime


def new_state_for_turn(
    *,
    turn_id: str,
    user_input: str,
    messages: list[Message],
    turn_seq: int,
) -> State:
    return {
        "messages": list(messages),
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
    }
