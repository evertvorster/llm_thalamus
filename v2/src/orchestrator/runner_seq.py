from __future__ import annotations

from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.final_node import build_final_request
from orchestrator.state import State


def run_turn_seq(state: State, deps: Deps) -> Iterator[Event]:
    """
    Sequential runner (pre-LangGraph).

    Streams thinking/response deltas live, but only the response stream becomes
    the final answer.
    """
    yield {"type": "node_start", "node": "final"}

    model, prompt = build_final_request(state, deps)

    response_parts: list[str] = []

    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue

        # Always show live progress in the thinking panel.
        yield {"type": "log", "text": text}

        # Only user-facing response becomes the final answer.
        if kind == "response":
            response_parts.append(text)

    answer = "".join(response_parts).strip()
    state["final"]["answer"] = answer
    state["runtime"]["node_trace"].append("final:ollama")

    yield {"type": "node_end", "node": "final"}
    yield {"type": "final", "answer": answer}
