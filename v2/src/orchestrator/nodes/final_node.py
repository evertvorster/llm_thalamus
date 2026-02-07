from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def _render_world_block(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return ""

    lines: list[str] = ["[WORLD]"]
    for k in ("now", "tz", "space", "updated_at"):
        v = w.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            lines.append(f"{k}: {s}")

    topics = w.get("topics")
    if isinstance(topics, list) and topics:
        lines.append(f"topics: {topics}")

    goals = w.get("goals")
    if isinstance(goals, list) and goals:
        lines.append(f"goals: {goals}")

    return "\n".join(lines) + "\n"


def _render_context_block(state: State) -> str:
    memories = state.get("context", {}).get("memories", []) or []
    if not memories:
        return ""

    lines = ["Context:"]
    for m in memories:
        text = str(m.get("text", "")).strip()
        if not text:
            continue
        ts = m.get("ts")
        ts = str(ts).strip() if ts is not None else ""
        if ts:
            lines.append(f'- "{text}" created at {ts}')
        else:
            lines.append(f"- {text}")

    return "\n" + "\n".join(lines) + "\n"


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    model = deps.models["final"]
    user_input = state["task"]["user_input"]

    prompt = deps.prompt_loader.render(
        "final",
        user_input=user_input,
        context=_render_context_block(state),
        world=_render_world_block(state),
    )
    return model, prompt
