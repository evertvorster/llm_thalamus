from __future__ import annotations

from orchestrator.state import State


def render_chat_history(state: State, *, max_turns: int = 6) -> str:
    """
    Prompt adapter: render a short transcript from state.context.chat_history or
    state.context.chat_history_text.

    This is NOT UI formatting. It exists solely to provide bounded prompt context.
    """
    ctx = state.get("context", {}) or {}

    # Prefer pre-rendered text if present.
    text = ctx.get("chat_history_text")
    if isinstance(text, str) and text.strip():
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        if max_turns > 0 and len(lines) > max_turns:
            lines = lines[-max_turns:]
        return "\n".join(lines).strip()

    turns = ctx.get("chat_history", []) or []
    if not isinstance(turns, list) or not turns:
        return ""

    tail = turns[-max_turns:] if max_turns > 0 else turns

    lines: list[str] = []
    for t in tail:
        if not isinstance(t, dict):
            continue
        role = (t.get("role") or "").strip()
        content = (t.get("content") or "").strip()
        if not content:
            continue
        if role:
            lines.append(f"{role}: {content}")
        else:
            lines.append(content)

    return "\n".join(lines).strip()


def render_memories_summary(state: State, *, max_items: int = 8, max_chars: int = 1200) -> str:
    """
    Prompt adapter: summarize state.context.memories (list[dict]) into a compact block.
    """
    ctx = state.get("context", {}) or {}
    mems = ctx.get("memories", []) or []
    if not isinstance(mems, list) or not mems:
        return ""

    lines: list[str] = []
    for m in mems[:max_items]:
        if not isinstance(m, dict):
            continue
        score = m.get("score")
        sector = m.get("sector")
        text = m.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        text = text.strip().replace("\n", " ")
        if not text:
            continue
        lines.append(f"- score={score} sector={sector}: {text}")

    out = "\n".join(lines).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out


def render_world_summary(state: State) -> str:
    """
    Prompt adapter: summarize stable keys from state.world.

    NOTE:
    This summary is used by routing/planning prompts.
    Include rules (and identity) so the planner/router behave correctly when the user
    is explicitly discussing world state.
    """
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return ""

    keys = ["now", "tz", "project", "topics", "goals", "rules", "identity", "updated_at"]
    lines: list[str] = []
    for k in keys:
        if k in w:
            lines.append(f"{k}: {w.get(k)}")
    return "\n".join(lines).strip()
