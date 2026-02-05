from __future__ import annotations

from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.final_node import build_final_request
from orchestrator.state import State


def run_turn_seq(state: State, deps: Deps) -> Iterator[Event]:
    """
    Sequential runner (pre-LangGraph). Emits events for the worker to forward.

    Streams deltas as they arrive (no buffering).
    """
    yield {"type": "node_start", "node": "final"}

    model, prompt = build_final_request(state, deps)

    parts: list[str] = []
    for chunk in deps.llm_generate_stream(model, prompt):
        text = str(chunk)
        if not text:
            continue
        parts.append(text)
        # stream each chunk immediately
        yield {"type": "log", "text": text}

    answer = "".join(parts).strip()
    state["final"]["answer"] = answer
    state["runtime"]["node_trace"].append("final:ollama")

    yield {"type": "node_end", "node": "final"}
    yield {"type": "final", "answer": answer}
