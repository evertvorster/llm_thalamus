from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Any


from orchestrator.deps import Deps
from orchestrator.state import State


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


# -------------------------
# JSON parsing (strict-ish)
# -------------------------

def _extract_json_object(text: str) -> str:
    """
    Extract the first JSON object from a string.
    This tolerates accidental preamble text (but the prompt asks for JSON-only).
    """
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in reflection output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("unterminated JSON object in reflection output")


def _coerce_str_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for x in v:
        if not isinstance(x, str):
            continue
        s = x.strip()
        if s:
            out.append(s)
    return out


def _is_json_object_only(text: str) -> bool:
    """
    Optional stricter check: JSON must begin/end with braces.
    We don't hard-fail here; prompt already instructs the model.
    """
    s = text.lstrip()
    e = text.rstrip()
    return s.startswith("{") and e.endswith("}")


def _parse_reflection_json(text: str) -> Tuple[List[str], dict]:
    blob = _extract_json_object(text)
    obj = json.loads(blob)

    if not isinstance(obj, dict):
        return ([], {})

    try:
        version = int(obj.get("version", 1))
    except Exception:
        version = 1
    if version != 1:
        return ([], {})

    memories = _coerce_str_list(obj.get("memories", []))
    world_delta = obj.get("world_delta", {})
    if not isinstance(world_delta, dict):
        world_delta = {}

    # world_delta can be {} or must contain only add/remove/set
    # Unknown keys are dropped to keep it deterministic.
    clean_delta: dict = {}
    for k in ("add", "remove", "set"):
        if k in world_delta and isinstance(world_delta[k], dict):
            clean_delta[k] = world_delta[k]
    if not clean_delta:
        clean_delta = {}

    return (memories, clean_delta)


# -------------------------
# World state load/commit
# -------------------------

def _state_root_from_cfg(deps: Deps) -> Path:
    # Consistent with your convention: <state_root>/log/thalamus.log
    return Path(deps.cfg.log_file).parent.parent


def _world_state_path(deps: Deps) -> Path:
    return _state_root_from_cfg(deps) / "world_state.json"


def _now_iso() -> str:
    return datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")


def _default_world(now_iso: str) -> dict:
    # Minimal + expandable. Unknown future keys are allowed via world_delta.set.
    return {
        "version": 1,
        "topics": [],
        "goals": [],
        "project": None,
        "updated_at": now_iso,
    }


def _load_world_state(path: Path, now_iso: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        w = _default_world(now_iso)
        _atomic_write_json(path, w)
        return w

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("world_state is not an object")
    except Exception:
        # Fail safe: replace with defaults rather than propagate corruption.
        w = _default_world(now_iso)
        _atomic_write_json(path, w)
        return w

    # Ensure required keys exist
    if data.get("version") != 1:
        data["version"] = 1
    data.setdefault("topics", [])
    data.setdefault("goals", [])
    data.setdefault("project", None)
    data.setdefault("updated_at", now_iso)

    # Normalize list types
    if not isinstance(data["topics"], list):
        data["topics"] = []
    if not isinstance(data["goals"], list):
        data["goals"] = []

    return data


def _atomic_write_json(path: Path, obj: dict) -> None:
    """
    Atomic replace: write temp file in same directory, fsync, rename.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)


def _deep_merge_set(target: dict, patch: dict) -> dict:
    """
    Apply a dict patch onto target:
      - dict values merge recursively
      - non-dict overwrites
      - explicit None overwrites (clears)
    """
    out = target
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge_set(out[k], v)
        else:
            out[k] = v
    return out


def _apply_add_remove(world: dict, add: dict, remove: dict) -> dict:
    """
    For list-like fields:
      - add[field] expects list[str] (or list[Any] coerced to str)
      - remove[field] expects list[str]
    If the target field isn't a list, we create it if add/remove is used.
    """
    def as_str_list(v: Any) -> List[str]:
        if not isinstance(v, list):
            return []
        out: List[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
        return out

    # Apply removals first (deterministic)
    for field, items in remove.items():
        if field == "updated_at":
            continue
        rm = as_str_list(items)
        if not rm:
            continue
        if not isinstance(world.get(field), list):
            world[field] = []
        world[field] = [x for x in world[field] if str(x) not in set(rm)]

    # Apply adds with exact-match dedupe
    for field, items in add.items():
        if field == "updated_at":
            continue
        ad = as_str_list(items)
        if not ad:
            continue
        if not isinstance(world.get(field), list):
            world[field] = []
        existing = set(str(x) for x in world[field])
        for x in ad:
            if x not in existing:
                world[field].append(x)
                existing.add(x)

    return world


def commit_world_delta(path: Path, world_before: dict, delta: dict, now_iso: str) -> dict:
    """
    Deterministic merge:
      - world_delta.add/remove apply to list fields
      - world_delta.set applies deep dict merge / overwrite
      - updated_at set by controller time
    """
    world_after = deepcopy(world_before)

    add = delta.get("add", {}) if isinstance(delta.get("add", {}), dict) else {}
    remove = delta.get("remove", {}) if isinstance(delta.get("remove", {}), dict) else {}
    set_patch = delta.get("set", {}) if isinstance(delta.get("set", {}), dict) else {}

    world_after = _apply_add_remove(world_after, add=add, remove=remove)
    world_after = _deep_merge_set(world_after, set_patch)

    world_after["version"] = 1
    world_after["updated_at"] = now_iso

    _atomic_write_json(path, world_after)
    return world_after


# -------------------------
# Reflection rendering
# -------------------------

def _render_world_for_reflection(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return "(empty)"

    # Compact, stable view (don’t dump nested arbitrarily)
    keys = []
    for k in ("now", "tz", "project", "updated_at", "version"):
        if k in w and w[k] is not None:
            keys.append(f"{k}: {w[k]}")
    if isinstance(w.get("topics"), list):
        keys.append(f"topics: {w.get('topics')}")
    if isinstance(w.get("goals"), list):
        keys.append(f"goals: {w.get('goals')}")
    return "\n".join(keys) if keys else "(empty)"


def _render_context_for_reflection(ctx_mems: list[dict]) -> str:
    lines: List[str] = []
    for m in ctx_mems or []:
        text = str(m.get("text", "") or "").strip()
        if not text:
            continue
        ts = str(m.get("ts", "") or "").strip()
        if ts:
            lines.append(f'- "{text}" created at {ts}')
        else:
            lines.append(f'- "{text}"')
    return "\n".join(lines) if lines else "(empty)"


# -------------------------
# Main entry
# -------------------------

def run_reflect_store_node(
    state: State,
    deps: Deps,
    *,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Post-turn reflection + memory storage + world delta commit.

    Reflection must receive the same context/world as final:
      - state["context"]["memories"] (if retrieval ran)
      - state["world"] (if world_fetch ran)
      - user message and final answer

    Side effects:
      - deps.openmemory.add() per stored memory
      - world_state.json committed atomically if world_delta non-empty
    """
    model = deps.models.get("agent")
    if not model:
        raise RuntimeError("No model configured for reflection (expected 'agent')")

    user_msg = state["task"]["user_input"]
    answer = state["final"]["answer"]

    ctx_mems = state.get("context", {}).get("memories", []) or []
    context_text = _render_context_for_reflection(ctx_mems)
    world_text = _render_world_for_reflection(state)

    referenced_texts: Set[str] = {
        str(m.get("text", "") or "").strip()
        for m in ctx_mems
        if isinstance(m, dict) and str(m.get("text", "") or "").strip()
    }

    prompt = deps.prompt_loader.render(
        "reflect_store",
        user_message=user_msg,
        assistant_message=answer,
        referenced_memories="(deprecated)",
        world=world_text,
        context=context_text,
    )

    response_parts: List[str] = []
    started_response = False

    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue

        if kind == "response":
            if not started_response:
                started_response = True
                # Ensure the JSON starts on a new line in the thinking stream
                if on_delta is not None:
                    on_delta("\n")
            response_parts.append(text)

        if on_delta is not None:
            on_delta(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return

    try:
        memories, world_delta = _parse_reflection_json(reflection_text)
    except Exception as e:
        if on_delta is not None:
            on_delta(f"\n[reflect_store] JSON parse failed: {e}\n")
        state["runtime"]["node_trace"].append("reflect_store:parse_fail")
        return

    # Store memories (exact-match dedupe vs referenced + within-output).
    stored = 0
    seen_out: Set[str] = set()
    for mem in memories:
        mem = mem.strip()
        if not mem:
            continue
        if mem in referenced_texts:
            continue
        if mem in seen_out:
            continue
        seen_out.add(mem)

        deps.openmemory.add(mem)
        stored += 1
        if on_memory_saved is not None:
            on_memory_saved(mem)

    # Commit world delta if present and non-empty
    committed = False
    if isinstance(world_delta, dict) and any(k in world_delta for k in ("add", "remove", "set")):
        # treat empty dicts as no-op
        add = world_delta.get("add") if isinstance(world_delta.get("add"), dict) else {}
        remove = world_delta.get("remove") if isinstance(world_delta.get("remove"), dict) else {}
        setp = world_delta.get("set") if isinstance(world_delta.get("set"), dict) else {}

        if add or remove or setp:
            now_iso = _now_iso()
            ws_path = _world_state_path(deps)

            world_before = _load_world_state(ws_path, now_iso=now_iso)
            _ = commit_world_delta(ws_path, world_before, delta=world_delta, now_iso=now_iso)
            committed = True
            if on_delta is not None:
                on_delta("\n[world_commit] applied\n")

    state["runtime"]["node_trace"].append(
        f"reflect_store:mem={stored},world_commit={'yes' if committed else 'no'}"
    )
