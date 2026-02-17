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


class RuntimeState(TypedDict, total=False):
    task: RuntimeTask
    runtime: RuntimeRuntime
    final: RuntimeFinal
    world: dict[str, Any]


State = dict[str, Any]


def new_runtime_state(*, user_text: str) -> State:
    # Keep shape stable even as we later add world/reflection/episodic nodes.
    return {
        "task": {"user_text": user_text, "language": "en"},
        "runtime": {"node_trace": [], "status": ""},
        "final": {"answer": ""},
        # World is intentionally empty in the stripped phase.
        "world": {},
    }
