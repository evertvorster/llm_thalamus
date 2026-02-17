from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Set, Tuple

from orchestrator.deps import Deps
from orchestrator.state import State
from orchestrator.world_state import WorldDelta, WorldState, commit_world_state, load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))


def _coerce_str_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for x in v:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _strip_code_fence(text: str) -> str:
    """
    Accept a single fenced code block wrapping the JSON output, e.g.:

      ```json
      { ... }
      ```

    If present, return only the fenced content. Otherwise return input unchanged.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s

    # Find end of first line (``` or ```json)
    first_nl = s.find("\n")
    if first_nl == -1:
        return s

    # Must end with a closing fence on its own line or at least "```"
    end = s.rfind("```")
    if end <= first_nl:
        return s

    inner = s[first_nl + 1 : end].strip()
    return inner


def _parse_json_block(text: str) -> str:
    """
    Extract the first JSON object from a text block. This defends against models that
    accidentally prepend/append commentary, and also supports JSON wrapped in a single
    fenced code block.
    """
    s = _strip_code_fence(text).strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in reflect_store output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("unterminated JSON object in reflect_store output")


def _parse_typed_world_delta(obj: Any) -> WorldDelta:
    """
    Reflect is responsible for TOPIC tracking only.

    Structural world updates (project/goals/rules/identity) are handled by world_update.
    We therefore accept only:
      - topics_add
      - topics_remove
    """
    if not isinstance(obj, dict):
        return {}

    d: WorldDelta = {}

    for k in ("topics_add", "topics_remove"):
        if k in obj:
            d[k] = _coerce_str_list(obj.get(k))  # type: ignore[assignment]

    # All-empty => no-op
    if not d.get("topics_add") and not d.get("topics_remove"):
        return {}

    return d


def _parse_reflection_json(text: str) -> Tuple[List[str], WorldDelta, List[str]]:
    """
    Parse reflection output.

    Expected format (no versioning):
      {
        "memories": ["..."],
        "world_delta": { ... }
      }

    Returns:
      (memories, typed_world_delta, dropped_world_delta_keys)
    """
    blob = _parse_json_block(text)
    obj = json.loads(blob)
    if not isinstance(obj, dict):
        raise ValueError("reflection JSON must be an object")

    # Strict keys expected; missing keys treated as empty.
    memories = _coerce_str_list(obj.get("memories", []))

    world_delta_raw = obj.get("world_delta", {})
    dropped_keys: List[str] = []
    if isinstance(world_delta_raw, dict):
        allowed = {"topics_add", "topics_remove"}
        dropped_keys = [k for k in world_delta_raw.keys() if k not in allowed]

    delta = _parse_typed_world_delta(world_delta_raw)

    # all-empty => no-op
    if not any(
        [
            delta.get("topics_add"),
            delta.get("topics_remove"),
        ]
    ):
        delta = {}

    return memories, delta, dropped_keys


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
      world_after if committed, else None.
    """
    if "reflect" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.reflect is required for reflect_store node")

    user_message = str(state.get("task", {}).get("user_input", "") or "")
    assistant_message = str(state.get("runtime", {}).get("final", "") or "")
    context = state.get("context") or {}
    world = world_before or (state.get("world") or {})

    if world_state_path is None:
        # Default path: <log_file parent>/../world_state.json
        world_state_path = Path(deps.cfg.log_file).parent.parent / "world_state.json"

    now_iso = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")

    # Load world if caller didn't provide.
    if world_before is None:
        try:
            world_before = load_world_state(path=world_state_path, now_iso=now_iso)
        except Exception:
            world_before = load_world_state(path=world_state_path, now_iso=now_iso)

    # Build prompt (compact JSON to conserve tokens)
    prompt = deps.prompt_loader.render(
        "reflect_store",
        user_message=user_message,
        assistant_message=assistant_message,
        world=json.dumps(world, ensure_ascii=False, separators=(",", ":")),
        context=json.dumps(context, ensure_ascii=False, separators=(",", ":")),
    )

    # Stream response
    response_parts: List[str] = []
    started_response = False
    for kind, text in deps.llm_generate_stream(deps.models["reflect"], prompt):
        if not text:
            continue

        if kind == "response":
            if not started_response:
                started_response = True
                if on_delta is not None:
                    on_delta("\n[reflect reply]\n")
            response_parts.append(text)

        if on_delta is not None:
            on_delta(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return None

    try:
        memories, world_delta, dropped_keys = _parse_reflection_json(reflection_text)
    except Exception as e:
        if on_delta is not None:
            on_delta(f"\n[reflect_store] JSON parse failed: {e}\n")
        state["runtime"]["node_trace"].append("reflect_store:parse_fail")
        return None

    if dropped_keys and on_delta is not None:
        on_delta(f"\n[reflect_store] dropped disallowed world_delta keys: {dropped_keys}\n")

    # Store memories (exact-match dedupe vs referenced + within-output).
    stored = 0
    saved_memories: List[str] = []
    seen_out: Set[str] = set()
    for mem in memories:
        m = str(mem).strip()
        if not m:
            continue

        key = m.lower()
        if key in seen_out:
            continue
        seen_out.add(key)

        # Skip if already referenced in context this turn.
        referenced = context.get("memories") or []
        if isinstance(referenced, list):
            if any(str(x).strip().lower() == key for x in referenced):
                continue

        try:
            deps.openmemory.add(m)
            stored += 1
            saved_memories.append(m)
            if on_memory_saved is not None:
                on_memory_saved(m)
        except Exception as e:
            if on_delta is not None:
                on_delta(f"\n[reflect_store] openmemory.add failed: {e}\n")
            continue

    # Emit stored memories to thinking log for transparency.
    if on_delta is not None:
        if saved_memories:
            on_delta("\n[reflect_store] stored memories:\n")
            for m in saved_memories:
                on_delta(f"- {m}\n")
        else:
            on_delta("\n[reflect_store] stored memories: (none)\n")

    # Persist reflection snapshot into runtime (worker stores it into episodic DB)
    state["runtime"]["reflection"] = {
        "memories_saved": saved_memories,
        "world_delta": world_delta,
    }

    # Commit world delta (topics-only). If no delta, no commit.
    world_after: Optional[WorldState] = None
    if world_delta:
        try:
            # IMPORTANT:
            # Always reload the latest world from disk before committing.
            latest_world = load_world_state(path=world_state_path, now_iso=now_iso)

            world_after = commit_world_state(
                path=world_state_path,
                world_before=latest_world,
                delta=world_delta,
                now_iso=now_iso,
            )

            # Keep in-memory state aligned for any downstream logic.
            state["world"] = dict(world_after)

        except Exception as e:
            if on_delta is not None:
                on_delta(f"\n[reflect_store] world commit failed: {e}\n")
            state["runtime"]["node_trace"].append("reflect_store:commit_fail")
            return None

    # Trace + small report
    state["runtime"]["node_trace"].append("reflect_store:ok")
    state["runtime"]["reports"].append(
        {
            "node": "reflect_store",
            "status": "ok",
            "summary": f"reflect_store saved_memories={stored} world_delta_keys={list(world_delta.keys()) if world_delta else []}",
            "tags": ["reflect_store"],
        }
    )

    return world_after
