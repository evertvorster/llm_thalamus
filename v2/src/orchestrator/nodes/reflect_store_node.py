from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Tuple

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import WorldDeltaV1, WorldStateV1, commit_world_state, load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


def _extract_json_object(text: str) -> str:
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


def _parse_typed_world_delta(obj: Any) -> WorldDeltaV1:
    if not isinstance(obj, dict):
        return {}

    d: WorldDeltaV1 = {}

    for k in ("topics_add", "topics_remove", "goals_add", "goals_remove"):
        if k in obj:
            d[k] = _coerce_str_list(obj.get(k))  # type: ignore[assignment]

    if "set_project" in obj:
        v = obj.get("set_project")
        if v is None:
            d["set_project"] = None
        elif isinstance(v, str):
            s = v.strip()
            d["set_project"] = s if s else None

    return d


def _parse_reflection_json(text: str) -> Tuple[List[str], WorldDeltaV1]:
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

    world_delta_raw = obj.get("world_delta", {})
    delta = _parse_typed_world_delta(world_delta_raw)

    # all-empty => no-op
    if not any(
        [
            delta.get("topics_add"),
            delta.get("topics_remove"),
            delta.get("goals_add"),
            delta.get("goals_remove"),
            "set_project" in delta,  # explicit set_project is meaningful even if None
        ]
    ):
        delta = {}

    return (memories, delta)


def _now_iso() -> str:
    return datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")


def _render_world_for_reflection(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return "(empty)"

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


def run_reflect_store_node(
    state: State,
    deps: Deps,
    *,
    # Compatibility: older caller passes these. Prefer them if provided.
    world_before: Optional[WorldStateV1] = None,
    world_state_path: Optional[Path] = None,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> Optional[WorldStateV1]:
    """
    Post-turn reflection + memory storage + STRICT world delta commit.

    Returns:
      - world_after if a commit happened (only if world_before was provided, or we loaded it)
      - None if no commit happened
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
                if on_delta is not None:
                    on_delta("\n")
            response_parts.append(text)

        if on_delta is not None:
            on_delta(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return None

    try:
        memories, world_delta = _parse_reflection_json(reflection_text)
    except Exception as e:
        if on_delta is not None:
            on_delta(f"\n[reflect_store] JSON parse failed: {e}\n")
        state["runtime"]["node_trace"].append("reflect_store:parse_fail")
        return None

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

    # Commit strict world delta if present
    committed = False
    world_after: Optional[WorldStateV1] = None

    if world_delta:
        now_iso = _now_iso()

        if world_state_path is None:
            # default path convention
            world_state_path = Path(deps.cfg.log_file).parent.parent / "world_state.json"

        if world_before is None:
            world_before = load_world_state(path=world_state_path, now_iso=now_iso)

        world_after = commit_world_state(
            path=world_state_path,
            world_before=world_before,
            delta=world_delta,
            now_iso=now_iso,
        )
        committed = True
        if on_delta is not None:
            on_delta("\n[world_commit] applied\n")

    state["runtime"]["node_trace"].append(
        f"reflect_store:mem={stored},world_commit={'yes' if committed else 'no'}"
    )

    return world_after
