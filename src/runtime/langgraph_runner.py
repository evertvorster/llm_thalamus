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


def _debug_state_view(state: State) -> dict:
    """Create a JSON-safe, size-limited view of the runtime State for debugging UI."""

    def _sanitize(obj, depth: int = 0):
        if depth > 6:
            return "…"
        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, str):
            if len(obj) > 8000:
                return obj[:8000] + "…(truncated)"
            return obj
        if isinstance(obj, dict):
            out = {}
            for k in sorted(obj.keys(), key=lambda x: str(x)):
                if str(k).startswith("_"):
                    continue

                # Drop non-serializable runtime internals
                if depth == 0 and k == "runtime":
                    rt = obj.get(k) or {}
                    if isinstance(rt, dict):
                        rt2 = {}
                        for rk in sorted(rt.keys(), key=lambda x: str(x)):
                            if rk in ("emitter",):
                                continue
                            rt2[str(rk)] = _sanitize(rt.get(rk), depth + 1)
                        out["runtime"] = rt2
                    continue

                out[str(k)] = _sanitize(obj.get(k), depth + 1)
            return out
        if isinstance(obj, (list, tuple)):
            items = list(obj)
            if len(items) > 200:
                items = items[:200] + ["…(truncated)"]
            return [_sanitize(x, depth + 1) for x in items]

        s = repr(obj)
        if len(s) > 2000:
            s = s[:2000] + "…"
        return s

    view: dict[str, object] = {}
    for k in ("task", "context", "final", "world", "runtime"):
        if k in state:
            view[k] = _sanitize(state.get(k), 0)
    return view


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

    # Populate time fields in State.runtime from RuntimeServices.tool_resources.
    rt = state.setdefault("runtime", {})

    res = services.tool_resources
    now_iso = str(getattr(res, "now_iso", "") or "")
    tz = str(
        getattr(res, "tz", "") or
        getattr(res, "timezone", "") or
        ""
    )

    if now_iso and not str(rt.get("now_iso") or ""):
        rt["now_iso"] = now_iso

    if tz and not str(rt.get("timezone") or ""):
        rt["timezone"] = tz

    # Optional: provide an epoch timestamp for convenience/debugging.
    # (Safe even if now_iso is missing or non-ISO.)
    if "timestamp" not in rt or not rt.get("timestamp"):
        try:
            from datetime import datetime
            rt["timestamp"] = int(datetime.fromisoformat(rt.get("now_iso", "")).timestamp())
        except Exception:
            pass
        
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

        # Emit a sanitized state snapshot for debugging UI at node boundaries.
        try:
            et = ev.get("type")
            if et in ("turn_start", "node_start", "node_end"):
                node_id = str(ev.get("node_id") or "")
                span_id = str(ev.get("span_id") or "")
                if node_id and span_id:
                    bus.emit(
                        factory.state_update(
                            node_id=node_id,
                            span_id=span_id,
                            when=et,
                            state=_debug_state_view(state),
                        )
                    )
        except Exception:
            pass

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
