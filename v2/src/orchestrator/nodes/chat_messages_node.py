from __future__ import annotations

from typing import Any

from chat_history import read_tail
from orchestrator.deps import Deps
from orchestrator.state import State


def _render_history_text(turns: list[Any]) -> str:
    """
    Stable, prompt-friendly rendering.
    Turns are ChatTurn-like objects with .role .content .ts (as returned by read_tail()).
    """
    lines: list[str] = []
    for t in turns:
        role = getattr(t, "role", "") or ""
        content = (getattr(t, "content", "") or "").strip()
        ts = getattr(t, "ts", "") or ""
        if not content:
            continue
        if ts:
            lines.append(f"{role} ({ts}): {content}")
        else:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(empty)"


def run_chat_messages_node(state: State, deps: Deps) -> State:
    """
    Mechanical node: load the last N turns from the on-disk chat history.
    No LLM calls. No side effects. Deterministic output.

    Uses:
      - state.task.chat_history_k if > 0
      - else deps.cfg.history_message_limit

    Populates:
      state["context"]["chat_history"]      -> list[dict]{role, content, ts}
      state["context"]["chat_history_text"] -> rendered text block
    """
    task = state.get("task", {})
    k_req = task.get("chat_history_k", 0)
    try:
        k = int(k_req)
    except Exception:
        k = 0

    if k <= 0:
        k = int(deps.cfg.history_message_limit)

    # Hard clamp to keep prompts bounded and deterministic.
    if k < 0:
        k = 0
    if k > 50:
        k = 50

    turns = read_tail(deps.cfg.message_file, limit=k)

    history: list[dict] = []
    for t in turns:
        history.append(
            {
                "role": getattr(t, "role", ""),
                "content": getattr(t, "content", ""),
                "ts": getattr(t, "ts", ""),
            }
        )

    state["context"]["chat_history"] = history
    state["context"]["chat_history_text"] = _render_history_text(turns)
    state["runtime"]["node_trace"].append(f"chat_messages:k={k}")

    return state
