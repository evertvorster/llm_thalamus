from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


def _state_root_from_cfg(deps: Deps) -> Path:
    # matches prior worker logic: log/thalamus.log under <state_root>/log/
    return Path(deps.cfg.log_file).parent.parent


def run_world_fetch_node(state: State, deps: Deps) -> State:
    """
    Populate state["world"] with a view requested by router:
      - "none": no-op (should not be called)
      - "time": {now, tz}
      - "full": {now, tz, topics, goals, project, updated_at, version}
    """
    view = (state.get("task", {}).get("world_view") or "none").strip().lower()
    if view not in {"time", "full"}:
        state["world"] = {}
        return state

    now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")

    if view == "time":
        state["world"] = {
            "now": now_iso,
            "tz": "Africa/Windhoek",
        }
        return state

    # full snapshot from disk (create if missing)
    world_path = _state_root_from_cfg(deps) / "world_state.json"
    persistent = load_world_state(path=world_path, now_iso=now_iso)

    payload = dict(persistent)
    payload["now"] = now_iso
    payload["tz"] = "Africa/Windhoek"

    state["world"] = payload
    return state
