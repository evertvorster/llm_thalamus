from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Tuple

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import WorldDelta, WorldState, commit_world_state, load_world_state


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


def _coerce_identity_set(v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        return {}

    out: dict[str, str] = {}
    for k in ("user_name", "session_user_name", "agent_name", "user_location"):
        if k not in v:
            continue
        raw = v.get(k)
        if raw is None:
            out[k] = ""
            continue
        if isinstance(raw, str):
            out[k] = raw.strip()
        else:
            out[k] = str(raw).strip()
    return out


def _parse_typed_world_delta(obj: Any) -> WorldDelta:
    if not isinstance(obj, dict):
        return {}

    d: WorldDelta = {}

    for k in (
        "topics_add",
        "topics_remove",
        "goals_add",
        "goals_remove",
        "rules_add",
        "rules_remove",
    ):
        if k in obj:
            d[k] = _coerce_str_list(obj.get(k))  # type: ignore[assignment]

    if "set_project" in obj:
        v = obj.get("set_project")
        # Project is always a string; empty string clears.
        if v is None:
            d["set_project"] = ""
        elif isinstance(v, str):
            d["set_project"] = v.strip()
        else:
            d["set_project"] = str(v).strip()

    if "identity_set" in obj:
        ident = _coerce_identity_set(obj.get("identity_set"))
        if ident:
            d["identity_set"] = ident

    return d


def _parse_reflection_json(text: str) -> Tuple[List[str], WorldDelta]:
    """
    Parse reflection output.

    Expected format (no versioning):
      {
        "memories": ["..."],
        "world_delta": {...}   OR {}
      }
    """
    blob = _extract_json_object(text)
    obj = json.loads(blob)

    if not isinstance(obj, dict):
        return ([], {})

    # Strict keys expected; missing keys treated as empty.
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
            delta.get("rules_add"),
            delta.get("rules_remove"),
            "set_project" in delta,  # explicit set_project is meaningful even if empty
            "identity_set" in delta,
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

    keys: list[str] = []
    for k in ("now", "tz", "project", "updated_at"):
        if k in w and w[k] is not None and str(w[k]).strip():
            keys.append(f"{k}: {w[k]}")

    if isinstance(w.get("topics"), list):
        keys.append(f"topics: {w.get('topics')}")
    if isinstance(w.get("goals"), list):
        keys.append(f"goals: {w.get('goals')}")
    if isinstance(w.get("rules"), list):
        keys.append(f"rules: {w.get('rules')}")

    ident = w.get("identity")
    if isinstance(ident, dict):
        # Show only non-empty identity fields.
        for k in ("user_name", "session_user_name", "agent_name", "user_location"):
            v = ident.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                keys.append(f"identity.{k}: {s}")

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
    world_before: Optional[WorldState] = None,
    world_state_path: Optional[Path] = None,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> Optional[WorldState]:
    """
    Post-turn reflection + memory storage + STRICT world delta commit.

    Returns:
      - world_after if a commit happened (only if world_before was provided, or we loaded it)
      - None if no commit happened
    """
    model = deps.models.get("reflect")
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
    saved_memories: List[str] = []
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
        saved_memories.append(mem)
        if on_memory_saved is not None:
            on_memory_saved(mem)

    # Commit strict world delta if present
    committed = False
    world_after: Optional[WorldState] = None

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

    # --- expose reflection summary for downstream mechanical logging ---
    state["runtime"]["reflection"] = {
        "memories_saved": saved_memories,
        "world_delta": world_delta,
        "world_committed": committed,
        "world_before": world_before if world_before is not None else {},
        "world_after": world_after if world_after is not None else {},
    }

    state["runtime"]["node_trace"].append(
        f"reflect_store:mem={stored},world_commit={'yes' if committed else 'no'}"
    )

    return world_after
