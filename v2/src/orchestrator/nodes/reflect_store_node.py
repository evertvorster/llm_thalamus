from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import commit_world_state, load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)

_ALLOWED_WORLD_DELTA_KEYS = {
    "topics_add",
    "topics_remove",
    "goals_add",
    "goals_remove",
    "set_space",
}


def _extract_json_object(text: str) -> str:
    """
    Extract the first JSON object from a string.
    (Matches the router extraction style; strict parsing.)
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


def _coerce_str_list(v) -> List[str]:
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


def _normalize_world_delta(delta) -> dict:
    """
    Keep only allowed keys, normalize list fields, normalize set_space.
    Unknown keys are dropped.
    """
    if not isinstance(delta, dict):
        return {}

    clean: dict = {}
    for k in _ALLOWED_WORLD_DELTA_KEYS:
        if k not in delta:
            continue

        if k == "set_space":
            v = delta.get(k)
            if v is None:
                clean[k] = None
            else:
                s = str(v).strip()
                clean[k] = s if s else None
            continue

        # list fields
        clean[k] = _coerce_str_list(delta.get(k))

    # If everything is empty/None, treat as no-op
    if not clean:
        return {}
    all_empty = True
    for k, v in clean.items():
        if k == "set_space":
            if v is not None:
                all_empty = False
                break
        else:
            if isinstance(v, list) and len(v) > 0:
                all_empty = False
                break
    return {} if all_empty else clean


def _render_world_for_reflection(state: State) -> str:
    """
    Reflection must receive the same world payload as the final node.
    We render whatever is present in state["world"] (may be empty).
    """
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return "(empty)"

    # Keep stable and compact.
    # We do NOT dump arbitrary nested structures.
    lines: List[str] = []
    for key in ("now", "tz", "space", "updated_at", "version"):
        if key in w and w[key] is not None:
            lines.append(f"{key}: {w[key]}")
    if isinstance(w.get("topics"), list):
        lines.append(f"topics: {w.get('topics')}")
    if isinstance(w.get("goals"), list):
        lines.append(f"goals: {w.get('goals')}")
    return "\n".join(lines) if lines else "(empty)"


def _render_context_for_reflection(ctx_mems: list[dict]) -> str:
    """
    Reflection must receive the same context as the final node.
    Use the same human-readable rendering as before.
    """
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


def _state_root_from_cfg(deps: Deps) -> Path:
    # Consistent with your earlier convention: <state_root>/log/thalamus.log
    return Path(deps.cfg.log_file).parent.parent


def _world_state_path(deps: Deps) -> Path:
    return _state_root_from_cfg(deps) / "world_state.json"


def _parse_reflection_json(text: str) -> Tuple[List[str], dict]:
    """
    Returns:
      - memories: list[str]
      - world_delta: dict (normalized; may be {})
    """
    blob = _extract_json_object(text)
    obj = json.loads(blob)

    if not isinstance(obj, dict):
        return ([], {})

    version = obj.get("version", 1)
    try:
        version = int(version)
    except Exception:
        version = 1
    if version != 1:
        # For now: reject unknown versions safely
        return ([], {})

    memories = _coerce_str_list(obj.get("memories", []))
    world_delta = _normalize_world_delta(obj.get("world_delta", {}))
    return (memories, world_delta)


def run_reflect_store_node(
    state: State,
    deps: Deps,
    *,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Post-turn reflection + memory storage + world delta commit.

    Invariants:
      - Reflection receives the same context/world that final saw (from State).
      - Reflection output is strict JSON.
      - Only derived facts are stored as memories (enforced by prompt).
      - World state is committed ONLY here, using deterministic merge rules.

    Side effects:
      - deps.openmemory.add() per stored memory (exact-match dedupe only)
      - commit_world_state(...) if world_delta is non-empty
    """
    model = deps.models.get("agent")
    if not model:
        raise RuntimeError("No model configured for reflection (expected 'agent')")

    user_msg = state["task"]["user_input"]
    answer = state["final"]["answer"]

    ctx_mems = state.get("context", {}).get("memories", []) or []
    context_text = _render_context_for_reflection(ctx_mems)
    world_text = _render_world_for_reflection(state)

    # Exact-match dedupe uses referenced memories' raw text only (no timestamps).
    referenced_texts: Set[str] = {
        str(m.get("text", "") or "").strip()
        for m in ctx_mems
        if isinstance(m, dict) and str(m.get("text", "") or "").strip()
    }

    prompt = deps.prompt_loader.render(
        "reflect_store",
        user_message=user_msg,
        assistant_message=answer,
        # Keep the placeholder name "referenced_memories" out of the prompt now.
        # We pass context/world explicitly as the "same payload" guarantee.
        referenced_memories="(deprecated)",
        world=world_text,
        context=context_text,
    )

    response_parts: List[str] = []
    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue

        # Forward both thinking + response to the UI
        if on_delta is not None:
            on_delta(text)

        # Only response tokens form the machine output
        if kind == "response":
            response_parts.append(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return

    try:
        memories, world_delta = _parse_reflection_json(reflection_text)
    except Exception as e:
        # Parsing failure: do nothing; never corrupt world state.
        if on_delta is not None:
            on_delta(f"\n[reflect_store] JSON parse failed: {e}\n")
        state["runtime"]["node_trace"].append("reflect_store:parse_fail")
        return

    # Store memories (exact-match dedupe against referenced + within-output).
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

    # Commit world delta (if any)
    committed = False
    if world_delta:
        now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")
        ws_path = _world_state_path(deps)

        world_before = load_world_state(path=ws_path, now_iso=now_iso)
        _ = commit_world_state(
            path=ws_path,
            world_before=world_before,
            delta=world_delta,  # deterministic merge
            now_iso=now_iso,
        )
        committed = True

        if on_delta is not None:
            on_delta("\n[world_commit] applied\n")

    state["runtime"]["node_trace"].append(
        f"reflect_store:mem={stored},world_commit={'yes' if committed else 'no'}"
    )
