from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.prompt_blocks import render_chat_history, render_world_summary
from orchestrator.state import State
from orchestrator.world_state import WorldDelta, WorldState, commit_world_state, load_world_state


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


def _now_iso() -> str:
    return datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")


def _extract_json_object(text: str) -> str:
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in world_update output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("unterminated JSON object in world_update output")


def _collect_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None] | None = None,
) -> str:
    """
    Collect the streamed response into a single string.

    UI contract (when emit is provided):
      - forward every streamed chunk as Event(type="log") so the UI receives "thinking" deltas
      - do not tag or prefix text; keep output raw/unchanged
    """
    response_parts: list[str] = []
    for kind, chunk in deps.llm_generate_stream(model, prompt):
        if not chunk:
            continue
        if emit is not None:
            emit({"type": "log", "text": chunk})
        if kind == "response":
            response_parts.append(chunk)
    return "".join(response_parts).strip()


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


def _coerce_identity_set(v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        return {}

    out: dict[str, str] = {}
    for k in ("user_name", "session_user_name", "agent_name", "user_location"):
        if k not in v:
            continue
        out[k] = _coerce_str(v.get(k))
    return out


def _parse_typed_world_delta(obj: Any) -> WorldDelta:
    """
    World-update is *explicit* world mutation. We accept only:
      - set_project
      - goals_add/goals_remove
      - rules_add/rules_remove
      - identity_set
    """
    if not isinstance(obj, dict):
        return {}

    d: WorldDelta = {}

    for k in ("goals_add", "goals_remove", "rules_add", "rules_remove"):
        if k in obj:
            d[k] = _coerce_str_list(obj.get(k))  # type: ignore[assignment]

    if "set_project" in obj:
        d["set_project"] = _coerce_str(obj.get("set_project"))

    if "identity_set" in obj:
        ident = _coerce_identity_set(obj.get("identity_set"))
        if ident:
            d["identity_set"] = ident  # type: ignore[assignment]

    # all-empty => no-op
    if not any(
        [
            d.get("goals_add"),
            d.get("goals_remove"),
            d.get("rules_add"),
            d.get("rules_remove"),
            "set_project" in d,  # explicit clear is meaningful
            "identity_set" in d,
        ]
    ):
        return {}

    return d


def _compute_world_state_path(deps: Deps) -> Path:
    """
    Prefer cfg.state_root if present, else fall back to:
      <log_file parent>/../world_state.json
    (Matches ControllerWorker + reflect_store conventions.)
    """
    sr = getattr(deps.cfg, "state_root", None)
    if sr:
        return Path(sr) / "world_state.json"
    return Path(deps.cfg.log_file).parent.parent / "world_state.json"


def run_world_update_node(
    state: State,
    deps: Deps,
    *,
    emit: Callable[[Event], None] | None = None,
) -> State:
    """
    Apply explicit world updates requested by the planner/executor.

    Inputs:
      state["runtime"]["next_step"].args:
        - requested_update: free-text instruction OR omitted to use task.user_input

    Output:
      - commits via commit_world_state()
      - updates state["world"] in-memory so downstream nodes see changes
      - appends runtime.reports entry

    LLM:
      - uses deps.models["tools"] (classified as tool step), produces JSON with "world_delta".
    """
    if "tools" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.tools is required for world_update node")

    step = state.get("runtime", {}).get("next_step", {}) or {}
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    requested_update = str(args.get("requested_update") or "").strip() or str(
        state.get("task", {}).get("user_input") or ""
    ).strip()

    prompt = deps.prompt_loader.render(
        "world_update",
        user_input=requested_update,
        world_summary=render_world_summary(state),
        chat_history=render_chat_history(state, max_turns=8),
    )

    raw = _collect_response(deps, model=deps.models["tools"], prompt=prompt, emit=emit)

    try:
        blob = _extract_json_object(raw)
        data = json.loads(blob)
    except Exception as e:
        state["runtime"]["reports"].append(
            {
                "node": "world_update",
                "status": "error",
                "summary": f"World update parse failed: {e}",
                "tags": ["world_update", "parse"],
            }
        )
        return state

    if not isinstance(data, dict):
        data = {}

    delta_raw = data.get("world_delta", {})
    delta = _parse_typed_world_delta(delta_raw)

    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = "world_update completed"

    if not delta:
        # No-op is still a valid outcome
        state["runtime"]["reports"].append(
            {
                "node": "world_update",
                "status": "ok",
                "summary": "World update: no changes requested.",
                "tags": ["world_update", "noop"],
            }
        )
        return state

    now_iso = _now_iso()
    world_state_path = _compute_world_state_path(deps)

    # Prefer in-memory world if it looks like a persistent WorldState; otherwise load strict.
    world_before_any = state.get("world") or {}
    world_before: WorldState
    try:
        if isinstance(world_before_any, dict) and all(
            k in world_before_any for k in ("updated_at", "project", "topics", "goals", "rules", "identity")
        ):
            world_before = world_before_any  # type: ignore[assignment]
        else:
            world_before = load_world_state(path=world_state_path, now_iso=now_iso)
    except Exception:
        world_before = load_world_state(path=world_state_path, now_iso=now_iso)

    world_after = commit_world_state(
        path=world_state_path,
        world_before=world_before,
        delta=delta,
        now_iso=now_iso,
    )

    # Critical: update in-memory view so later nodes see it immediately this run.
    state["world"] = dict(world_after)

    if emit is not None:
        emit({"type": "log", "text": "\n[world_update] committed world_state.json\n"})

    state["runtime"]["reports"].append(
        {
            "node": "world_update",
            "status": "ok",
            "summary": summary,
            "details": f"delta={delta}",
            "tags": ["world_update", "commit"],
        }
    )

    state["runtime"]["node_trace"].append("world_update:committed")
    return state
