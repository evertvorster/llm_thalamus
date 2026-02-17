from __future__ import annotations

from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.state import State

from runtime.graph_build import build_compiled_graph
from runtime.graph_nodes import emit_final, emit_log, emit_node_end, emit_node_start


def run_turn_runtime(state: State, deps: Deps) -> Iterator[Event]:
    """
    Runs the new two-node runtime graph and yields events compatible with the existing UI.
    Controller can swap run_turn_langgraph -> run_turn_runtime later. :contentReference[oaicite:11]{index=11}
    """
    compiled = build_compiled_graph(deps)

    # We want node_start/node_end events. LangGraph doesn't emit those by default.
    # So we rely on the node_trace + our scratch log buffer set by nodes.
    #
    # Minimal approach for bootstrap:
    # - invoke graph
    # - replay node_trace as start/end
    #
    # As you expand, you’ll likely switch to explicit wrapper nodes to emit start/end in real time.
    state["runtime"]["node_trace"].clear()

    out = compiled.invoke(state)

    # Emit buffered log chunks (streamed by nodes into _runtime_logs)
    logs = out.pop("_runtime_logs", []) if isinstance(out, dict) else []
    for t in logs:
        yield emit_log(str(t))

    # Emit node start/end markers from trace (best-effort for now)
    for node_id in out["runtime"].get("node_trace", []):
        yield emit_node_start(node_id)
        yield emit_node_end(node_id)

    # Emit final
    answer = out["final"].get("answer", "") or ""
    yield emit_final(str(answer))
