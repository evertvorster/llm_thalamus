from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, TypedDict


# -------------------------
# Schema (minimal/stable)
# -------------------------

DEFAULT_TOPICS_MAX = 5


class Identity(TypedDict):
    user_name: str
    session_user_name: str
    agent_name: str
    user_location: str


class WorldState(TypedDict):
    updated_at: str  # ISO-8601 timestamp
    project: str
    topics: list[str]
    goals: list[str]
    rules: list[str]
    identity: Identity


class WorldDelta(TypedDict, total=False):
    # Snapshot-level changes are expressed as deltas.
    topics_add: list[str]
    topics_remove: list[str]
    goals_add: list[str]
    goals_remove: list[str]
    rules_add: list[str]
    rules_remove: list[str]
    set_project: str  # empty string clears
    identity_set: Dict[str, str]  # keys: user_name, session_user_name, agent_name, user_location


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


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _coerce_identity(v: Any) -> Identity:
    if not isinstance(v, dict):
        v = {}

    return {
        "user_name": _coerce_str(v.get("user_name")),
        "session_user_name": _coerce_str(v.get("session_user_name")),
        "agent_name": _coerce_str(v.get("agent_name")),
        "user_location": _coerce_str(v.get("user_location")),
    }


def _validate_and_normalize(raw: Any, *, now_iso: str) -> WorldState:
    """
    Validate/normalize raw JSON into WorldState.

    Rules:
      - Missing/invalid keys are replaced with safe defaults.
      - topics/goals/rules are exact-match deduped, order-preserving.
      - topics are truncated to DEFAULT_TOPICS_MAX.
      - updated_at is set to now_iso if missing/invalid.
      - project is always a string (empty string means "no project").
      - identity is always present with all keys (empty strings by default).
    """
    if not isinstance(raw, dict):
        raw = {}

    topics = _coerce_str_list(raw.get("topics"))
    goals = _coerce_str_list(raw.get("goals"))
    rules = _coerce_str_list(raw.get("rules"))

    project = _coerce_str(raw.get("project"))
    identity = _coerce_identity(raw.get("identity"))

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
    rules = _dedupe(rules)

    updated_at = raw.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        updated_at = now_iso

    return {
        "updated_at": str(updated_at).strip() or now_iso,
        "project": project,
        "topics": topics,
        "goals": goals,
        "rules": rules,
        "identity": identity,
    }


def ensure_world_state_file_exists(*, path: Path, now_iso: str) -> None:
    """Ensure world_state.json exists. If missing, create with defaults."""
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    default: WorldState = {
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
    _atomic_write_json(path, default)


def load_world_state(*, path: Path, now_iso: str) -> WorldState:
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

    # Write back to keep the file stable.
    _atomic_write_json(path, world)
    return world


def apply_world_delta(world: WorldState, delta: WorldDelta) -> WorldState:
    """
    Deterministic, testable delta application.

    - Exact-match only (no fuzzy logic)
    - Order preserved for existing items
    - New additions append
    - Topics truncated to DEFAULT_TOPICS_MAX
    """
    topics = list(world["topics"])
    goals = list(world["goals"])
    rules = list(world["rules"])
    project = world["project"]
    identity = dict(world["identity"])  # shallow copy

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

    if "rules_remove" in delta:
        rules = _remove(rules, delta.get("rules_remove", []) or [])
    if "rules_add" in delta:
        rules = _add(rules, delta.get("rules_add", []) or [])

    if "set_project" in delta:
        project = _coerce_str(delta.get("set_project"))

    if "identity_set" in delta:
        raw = delta.get("identity_set")
        if isinstance(raw, dict):
            for k in ("user_name", "session_user_name", "agent_name", "user_location"):
                if k in raw:
                    identity[k] = _coerce_str(raw.get(k))

    return {
        "updated_at": world["updated_at"],  # caller sets
        "project": project,
        "topics": topics,
        "goals": goals,
        "rules": rules,
        "identity": Identity(
            user_name=_coerce_str(identity.get("user_name")),
            session_user_name=_coerce_str(identity.get("session_user_name")),
            agent_name=_coerce_str(identity.get("agent_name")),
            user_location=_coerce_str(identity.get("user_location")),
        ),
    }


def commit_world_state(
    *,
    path: Path,
    world_before: WorldState,
    delta: WorldDelta,
    now_iso: str,
) -> WorldState:
    """Apply delta + write world_state.json atomically."""
    merged = apply_world_delta(world_before, delta)
    merged["updated_at"] = now_iso
    _atomic_write_json(path, merged)
    return merged


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomic-ish write: write temp file in same directory then replace."""
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
