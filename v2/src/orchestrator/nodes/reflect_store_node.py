from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Tuple

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import WorldDeltaV1, WorldStateV1, commit_world_state

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


def _parse_reflection_json(text: str) -> Tuple[List[str], WorldDeltaV1]:
    """
    Reflection output contract (v1):
      {
        "version": 1,
        "memories": ["..."],
        "world_delta": {
          "topics_add": [...],
          "topics_remove": [...],
          "goals_add": [...],
          "goals_remove": [...],
          "set_project": "..." | null
        }
      }

    We are strict about *what we accept*:
      - Unknown keys are dropped.
      - Wrong types become no-ops.
    """
    blob = _extract_json_object(text)
    obj = json.loads(blob)

    if not isinstance(obj, dict):
        return ([], WorldDeltaV1())

    try:
        version = int(obj.get("version", 1))
    except Exception:
        version = 1
    if version != 1:
        return ([], WorldDeltaV1())

    memories = _coerce_str_list(obj.get("memories", []))

    wd_raw = obj.get("world_delta", {})
    if not isinstance(wd_raw, dict):
        wd_raw = {}

    delta: WorldDeltaV1 = {}

    # strict typed keys only
    for k in ("topics_add", "topics_remove", "goals_add", "goals_remove"):
        if k in wd_raw:
            v = wd_raw.get(k)
            if isinstance(v, list):
                delta[k] = _coerce_str_list(v)  # type: ignore[assignment]

    if "set_project" in wd_raw:
        v = wd_raw.get("set_project")
        if v is None:
            delta["set_project"] = None
        elif isinstance(v, str):
            s = v.strip()
            delta["set_project"] = s if s else None

    return (memories, delta)


# -------------------------
# Rendering (for reflection)
# -------------------------

def _render_world_for_reflection(world: WorldStateV1) -> str:
    # Stable, minimal, deterministic projection.
    lines: List[str] = []
    lines.append(f"version: {world.get('version')}")
    lines.append(f"updated_at: {world.get('updated_at')}")
    lines.append(f"project: {world.get('project')}")
    lines.append(f"topics: {world.get('topics', [])}")
    lines.append(f"goals: {world.get('goals', [])}")
    return "\n".join(lines)


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


def _now_iso() -> str:
    return datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")


# -------------------------
# Main entry
# -------------------------

def run_reflect_store_node(
    state: State,
    deps: Deps,
    *,
    world_before: WorldStateV1,
    world_state_path: Path,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> Optional[WorldStateV1]:
    """
    Post-turn reflection + memory storage + strict world delta commit.

    Authoritative world rules:
      - world_state.py owns schema, normalization, delta semantics, persistence.
      - reflect_store_node must NOT load/repair/normalize world_state.json.
      - reflect_store_node only:
          1) asks LLM for a *typed* WorldDeltaV1
          2) commits it via commit_world_state()
          3) returns world_after (or None if no commit)

    Returns:
      - world_after if a non-empty delta was committed
      - None if no world change was committed
    """
    model = deps.models.get("agent")
    if not model:
        raise RuntimeError("No model configured for reflection (expected 'agent')")

    user_msg = state["task"]["user_input"]
    answer = state["final"]["answer"]

    ctx_mems = state.get("context", {}).get("memories", []) or []
    context_text = _render_context_for_reflection(ctx_mems)
    world_text = _render_world_for_reflection(world_before)

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
        memories, delta = _parse_reflection_json(reflection_text)
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

    # Commit world delta if it is non-empty (strict typed delta)
    committed = False
    world_after: Optional[WorldStateV1] = None

    def _has_meaningful_delta(d: WorldDeltaV1) -> bool:
        for k in ("topics_add", "topics_remove", "goals_add", "goals_remove", "set_project"):
            if k not in d:
                continue
            v = d.get(k)
            if isinstance(v, list) and v:
                return True
            if k == "set_project" and ("set_project" in d):
                # set_project explicitly present is meaningful even if None
                return True
        return False

    if _has_meaningful_delta(delta):
        now_iso = _now_iso()
        world_after = commit_world_state(
            path=world_state_path,
            world_before=world_before,
            delta=delta,
            now_iso=now_iso,
        )
        committed = True
        if on_delta is not None:
            on_delta("\n[world_commit] applied\n")

    state["runtime"]["node_trace"].append(
        f"reflect_store:mem={stored},world_commit={'yes' if committed else 'no'}"
    )

    return world_after
