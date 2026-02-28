from __future__ import annotations

from typing import Any, TypedDict


class RuntimeTask(TypedDict, total=False):
    user_text: str
    language: str


class RuntimeFinal(TypedDict, total=False):
    answer: str


class RuntimeRuntime(TypedDict, total=False):
    node_trace: list[str]
    status: str

    # Append-only issues channel visible to the answer node.
    issues: list[str]

    # Time context for this turn (used to interpret relative dates/times).
    now_iso: str
    timezone: str


class RuntimeContext(TypedDict, total=False):
    # Builder-style context object (aggregates multiple sources).
    complete: bool
    context: dict[str, Any]
    issues: list[str]


class RuntimeState(TypedDict, total=False):
    task: RuntimeTask
    runtime: RuntimeRuntime
    context: RuntimeContext
    final: RuntimeFinal
    world: dict[str, Any]


State = dict[str, Any]


def new_runtime_state(*, user_text: str) -> State:
    # Keep shape stable even as we later add world/reflection/memory/episodic nodes.
    return {
        "task": {"user_text": user_text, "language": "en"},
        "runtime": {
            "node_trace": [],
            "status": "",
            "issues": [],
            "now_iso": "",
            "timezone": "",
        },
        "context": {},
        "final": {"answer": ""},
        "world": {},
    }