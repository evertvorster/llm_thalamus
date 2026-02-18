from __future__ import annotations

import threading
import time
import uuid
from typing import Iterator

from runtime.deps import Deps
from runtime.services import RuntimeServices
from runtime.event_bus import EventBus
from runtime.emitter import TurnEmitter
from runtime.events import TurnEventFactory, TurnEvent
from runtime.graph_build import build_compiled_graph
from runtime.state import State


def _provider_name(deps: Deps) -> str:
    # Best-effort; do not depend on provider internals.
    return deps.provider.__class__.__name__.lower().replace("provider", "")


def run_turn_runtime(state: State, deps: Deps, services: RuntimeServices) -> Iterator[TurnEvent]:
    """Run the runtime graph and stream TurnEvents as they occur.

    Contract:
    - Yields TurnEvent v1 dictionaries in strict seq order (per-turn).
    - Node + thinking events are emitted while the graph is running (true streaming).
    - Assistant output is emitted by the answer node (NOT synthesized here), so it can arrive
      before downstream nodes like reflect complete.
    """
    compiled = build_compiled_graph(deps, services)

    # Ensure keys exist (defensive)
    state.setdefault("runtime", {}).setdefault("node_trace", [])
    state.setdefault("final", {}).setdefault("answer", "")
    state.setdefault("world", {})

    # Turn identity
    turn_id = str(state.get("runtime", {}).get("turn_id") or "")
    if not turn_id:
        turn_id = uuid.uuid4().hex
        state.setdefault("runtime", {})["turn_id"] = turn_id

    factory = TurnEventFactory(turn_id=turn_id)
    bus = EventBus.create()
    emitter = TurnEmitter(factory, bus.emit)

    # Install emitter for nodes to use.
    state.setdefault("runtime", {})["emitter"] = emitter

    # Emit turn_start immediately.
    user_text = str(state.get("task", {}).get("user_text", "") or "")
    emitter.start_turn(
        user_text=user_text,
        provider=_provider_name(deps),
        models={k: str(v.model) for k, v in (deps.roles or {}).items()},
    )

    t0_ms = int(time.time() * 1000)

    result_holder: dict[str, object] = {}

    def _run_graph() -> None:
        try:
            out = compiled.invoke(state)
            result_holder["out"] = out
        except Exception as e:
            result_holder["error"] = e

    th = threading.Thread(target=_run_graph, daemon=True)
    th.start()

    # Stream events emitted by nodes while invoke() runs.
    for ev in bus.events_live(is_done=lambda: not th.is_alive()):
        yield ev

    th.join()

    dt_ms = max(0, int(time.time() * 1000) - t0_ms)

    err = result_holder.get("error")
    if err is not None:
        # Finalize turn with an error.
        bus.emit(factory.turn_end_error(code="TURN_ERROR", message=str(err), details={}, duration_ms=dt_ms))
        bus.close()
        for ev in bus.events():
            yield ev
        raise err  # type: ignore[misc]

    out = result_holder.get("out")
    if not isinstance(out, dict):
        out = {}

    # Emit world_commit (best-effort).
    world_after = out.get("world")
    if not isinstance(world_after, dict):
        world_after = {}

    world_before = state.get("world")
    if not isinstance(world_before, dict):
        world_before = {}

    delta: dict[str, object] = {}
    for k, v in world_after.items():
        if world_before.get(k) != v:
            delta[k] = v

    bus.emit(factory.world_commit(world_before=world_before, world_after=world_after, delta=delta))

    bus.emit(factory.turn_end_ok(duration_ms=dt_ms))
    bus.close()

    for ev in bus.events():
        yield ev
