from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict


# -------------------------
# Schema (v1, minimal/stable)
# -------------------------

WORLD_STATE_VERSION = 1
DEFAULT_TOPICS_MAX = 5


class WorldStateV1(TypedDict):
    version: int
    topics: list[str]
    goals: list[str]
    space: str | None
    updated_at: str  # ISO-8601 timestamp


class WorldDeltaV1(TypedDict, total=False):
    # Snapshot-level changes are expressed as deltas.
    topics_add: list[str]
    topics_remove: list[str]
    goals_add: list[str]
    goals_remove: list[str]
    set_space: str | None


def _now_iso8601(now: datetime) -> str:
    # caller controls tz; we just stringify
    return now.isoformat(timespec="seconds")


def _coerce_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _coerce_space(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _validate_and_normalize(raw: Any, *, now_iso: str) -> WorldStateV1:
    """
    Validate/normalize raw JSON into WorldStateV1.

    Rules:
      - Missing/invalid keys are replaced with safe defaults.
      - version is enforced to WORLD_STATE_VERSION (v1).
      - topics/goals are exact-match deduped, order-preserving.
      - updated_at is set to now_iso if missing/invalid.
    """
    if not isinstance(raw, dict):
        raw = {}

    topics = _coerce_str_list(raw.get("topics"))
    goals = _coerce_str_list(raw.get("goals"))
    space = _coerce_space(raw.get("space"))

    # exact-match dedupe, preserve order
    def _dedupe(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for s in xs:
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    topics = _dedupe(topics)[:DEFAULT_TOPICS_MAX]
    goals = _dedupe(goals)

    updated_at = raw.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        updated_at = now_iso

    return WorldStateV1(
        version=WORLD_STATE_VERSION,
        topics=topics,
        goals=goals,
        space=space,
        updated_at=str(updated_at),
    )


def ensure_world_state_file_exists(*, path: Path, now_iso: str) -> None:
    """
    Ensure world_state.json exists. If missing, create with defaults.
    """
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    default = WorldStateV1(
        version=WORLD_STATE_VERSION,
        topics=[],
        goals=[],
        space=None,
        updated_at=now_iso,
    )
    _atomic_write_json(path, default)


def load_world_state(*, path: Path, now_iso: str) -> WorldStateV1:
    """
    Load world_state.json, creating it if missing.
    Normalizes invalid content safely.
    """
    ensure_world_state_file_exists(path=path, now_iso=now_iso)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # If file is corrupted, replace with defaults rather than crashing the UI.
        raw = {}

    world = _validate_and_normalize(raw, now_iso=now_iso)

    # If normalization changed anything material (including updated_at missing),
    # we write back to keep the file stable.
    _atomic_write_json(path, world)
    return world


def apply_world_delta(world: WorldStateV1, delta: WorldDeltaV1) -> WorldStateV1:
    """
    Deterministic, testable delta application.

    - Exact-match only (no fuzzy logic)
    - Order preserved for existing items
    - New additions append
    - Topics truncated to DEFAULT_TOPICS_MAX
    """
    topics = list(world["topics"])
    goals = list(world["goals"])
    space = world["space"]

    def _remove(xs: list[str], rm: list[str]) -> list[str]:
        rm_set = set(s.strip() for s in rm if isinstance(s, str) and s.strip())
        return [s for s in xs if s not in rm_set]

    def _add(xs: list[str], add: list[str]) -> list[str]:
        seen = set(xs)
        for v in add:
            if not isinstance(v, str):
                continue
            s = v.strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            xs.append(s)
        return xs

    if "topics_remove" in delta:
        topics = _remove(topics, delta.get("topics_remove", []) or [])
    if "topics_add" in delta:
        topics = _add(topics, delta.get("topics_add", []) or [])
    topics = topics[:DEFAULT_TOPICS_MAX]

    if "goals_remove" in delta:
        goals = _remove(goals, delta.get("goals_remove", []) or [])
    if "goals_add" in delta:
        goals = _add(goals, delta.get("goals_add", []) or [])

    if "set_space" in delta:
        space = _coerce_space(delta.get("set_space"))

    return WorldStateV1(
        version=WORLD_STATE_VERSION,
        topics=topics,
        goals=goals,
        space=space,
        updated_at=world["updated_at"],  # caller sets
    )


def commit_world_state(
    *,
    path: Path,
    world_before: WorldStateV1,
    delta: WorldDeltaV1,
    now_iso: str,
) -> WorldStateV1:
    """
    Apply delta + write world_state.json atomically.
    """
    merged = apply_world_delta(world_before, delta)
    merged["updated_at"] = now_iso
    _atomic_write_json(path, merged)
    return merged


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """
    Atomic-ish write: write temp file in same directory then replace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = path.parent

    fd, tmp_name = tempfile.mkstemp(prefix="._world_state.", suffix=".json", dir=str(tmp_dir))
    tmp_path = Path(tmp_name)

    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists() and tmp_path != path:
            try:
                tmp_path.unlink()
            except OSError:
                pass
