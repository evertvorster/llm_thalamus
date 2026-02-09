from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


def _state_root_from_cfg(deps: Deps) -> Path:
    return Path(deps.cfg.log_file).parent.parent


def run_world_fetch_node(state: State, deps: Deps) -> State:
    """
    Merge the persistent world snapshot into state["world"].

    Time (now/tz) is ALWAYS available via state["world"], created at turn start.
    This node is only for the persistent snapshot requested by router:
      - "full": {topics, goals, project, updated_at, version} merged into state["world"]

    If called with any other world_view, this is a no-op.
    """
    view = (state.get("task", {}).get("world_view") or "none").strip().lower()
    if view != "full":
        return state

    world = state.get("world")
    if not isinstance(world, dict):
        world = {}
        state["world"] = world

    now_iso = str(world.get("now") or "").strip()
    if not now_iso:
        now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")
        world["now"] = now_iso
        world.setdefault("tz", "Africa/Windhoek")

    world_path = _state_root_from_cfg(deps) / "world_state.json"
    persistent = load_world_state(path=world_path, now_iso=now_iso)

    for k, v in persistent.items():
        world[k] = v

    state["runtime"]["node_trace"].append("world_fetch:full")
    return state
