from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json


World = Dict[str, Any]


def default_world(*, now_iso: str = "", tz: str = "") -> World:
    """
    Minimal default. Expand later as needed.
    """
    w: World = {
        "updated_at": now_iso,
        "project": "",
        "topics": [],
        "goals": [],
        "rules": [],
        "identity": {
            "user_name": "",
            "session_user_name": "",
            "agent_name": "",
            "user_location": "",
        },
    }
    if tz:
        w["tz"] = tz
    return w


def load_world_state(*, path: Path, now_iso: str = "", tz: str = "") -> World:
    """
    Loads world_state.json. If missing, creates it with defaults.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        w = default_world(now_iso=now_iso, tz=tz)
        commit_world_state(path=path, world=w)
        return w

    try:
        w = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(w, dict):
            raise ValueError("world_state.json is not an object")
    except Exception:
        # If corrupted, reset to default rather than crashing UI boot.
        w = default_world(now_iso=now_iso, tz=tz)
        commit_world_state(path=path, world=w)
        return w

    # Keep updated_at fresh on load if provided
    if now_iso:
        w["updated_at"] = now_iso
    if tz and "tz" not in w:
        w["tz"] = tz
    return w


def commit_world_state(*, path: Path, world: World) -> None:
    """
    Writes world JSON atomically-ish (write then replace).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(world, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
