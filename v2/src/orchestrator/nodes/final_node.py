from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def _render_world_block(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return ""

    lines: list[str] = ["[WORLD]"]
    for k in ("now", "tz", "project", "updated_at"):
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

    # FIX: include full-world fields when present
    rules = w.get("rules")
    if isinstance(rules, list) and rules:
        lines.append(f"rules: {rules}")

    identity = w.get("identity")
    if identity is not None:
        # identity can be a dict or string; keep it lossless
        lines.append(f"identity: {identity}")

    return "\n".join(lines) + "\n"


def _render_context_block(state: State) -> str:
    lines: list[str] = []

    chat_text = str(state.get("context", {}).get("chat_history_text", "") or "").strip()
    if chat_text:
        lines.append("[RECENT CHAT]")
        lines.append(chat_text)

    memories = state.get("context", {}).get("memories", []) or []
    if memories:
        lines.append("[MEMORIES]")
        for m in memories:
            # Accept both legacy string memories and structured dict memories
            if isinstance(m, str):
                text = m.strip()
                if text:
                    lines.append(f"- {text}")
                continue

            if isinstance(m, dict):
                text = str(m.get("text", "") or "").strip()
                if not text:
                    continue
                ts = m.get("ts")
                ts = str(ts).strip() if ts is not None else ""
                if ts:
                    lines.append(f'- "{text}" created at {ts}')
                else:
                    lines.append(f"- {text}")
                continue

            # ignore unknown shapes

    # NEW: episodic summary (from episode_query_node)
    episodes_summary = str(state.get("context", {}).get("episodes_summary", "") or "").strip()
    if episodes_summary:
        lines.append("[EPISODIC MEMORIES]")
        lines.append(episodes_summary)

    if not lines:
        return ""

    return "\n" + "\n".join(lines) + "\n"


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    model = deps.models["final"]
    user_input = state["task"]["user_input"]

    status = str(state.get("runtime", {}).get("status", "") or "").strip()

    prompt = deps.prompt_loader.render(
        "final",
        user_input=user_input,
        status=status,
        context=_render_context_block(state),
        world=_render_world_block(state),
    )
    return model, prompt
