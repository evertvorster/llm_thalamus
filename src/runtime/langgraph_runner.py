from __future__ import annotations

from typing import Iterator, Dict, Any

from runtime.deps import Deps
from runtime.graph_build import build_compiled_graph
from runtime.state import State


Event = Dict[str, Any]


def run_turn_runtime(state: State, deps: Deps) -> Iterator[Event]:
    """
    Runtime-native runner that yields the same event dict contract the UI already expects:
      - node_start/node_end/log/final
    """
    compiled = build_compiled_graph(deps)

    # Ensure keys exist (defensive; cheap)
    state.setdefault("runtime", {}).setdefault("node_trace", [])
    state.setdefault("final", {}).setdefault("answer", "")

    # Invoke the graph (nodes will buffer log chunks in state["_runtime_logs"])
    out = compiled.invoke(state)

    # Emit node spans (best-effort: trace is appended by nodes)
    trace = out.get("runtime", {}).get("node_trace", []) or []
    for node_id in trace:
        yield {"type": "node_start", "node": node_id}

        # If the node buffered logs, flush them here. This is not “true streaming” yet,
        # but it keeps the UI contract stable while we bootstrap.
        logs = out.pop("_runtime_logs", None)
        if isinstance(logs, list):
            for t in logs:
                yield {"type": "log", "text": str(t)}

        yield {"type": "node_end", "node": node_id}

    answer = str(out.get("final", {}).get("answer", "") or "")
    yield {"type": "final", "answer": answer}
