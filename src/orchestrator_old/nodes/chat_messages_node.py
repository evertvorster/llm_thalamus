from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State

# IMPORTANT:
# Use the same implementation the UI uses (ground truth).
from chat_history.message_history import format_for_prompt, read_tail  # noqa: E402


def run_chat_messages_node(state: State, deps: Deps) -> State:
    """
    Mechanical node: load the last N turns from the on-disk chat history.
    No LLM calls. No side effects. Deterministic output.

    Uses:
      - state.task.chat_history_k if > 0
      - else deps.cfg.history_message_limit

    Populates:
      state["context"]["chat_history"]      -> list[dict]{role, content, ts}
      state["context"]["chat_history_text"] -> rendered text block (exact UI formatter)
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

    # Ground-truth tail reader (same as UI)
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

    # Ground-truth prompt formatting (same as UI)
    state["context"]["chat_history_text"] = format_for_prompt(turns)

    state["runtime"]["node_trace"].append(f"chat_messages:k={k}")
    return state
