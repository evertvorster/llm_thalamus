from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def _render_chat_history(state: State) -> str:
    text = (state.get("context", {}).get("chat_history_text") or "").strip()
    return text if text else "(empty)"


def _render_memories_summary(state: State, *, max_items: int = 8) -> str:
    mems = state.get("context", {}).get("memories", []) or []
    if not isinstance(mems, list) or not mems:
        return "(empty)"

    lines: list[str] = []
    for m in mems[:max_items]:
        if not isinstance(m, dict):
            continue
        t = str(m.get("text", "") or "").strip()
        if not t:
            continue
        ts = str(m.get("ts", "") or "").strip()
        if ts:
            lines.append(f'- "{t}" (ts={ts})')
        else:
            lines.append(f'- "{t}"')
    return "\n".join(lines) if lines else "(empty)"


def _render_world_summary(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return "(empty)"

    # Only show persistent-ish keys; now/tz are already shown separately.
    keys = []
    for k in ("project", "topics", "goals", "updated_at", "version"):
        if k in w:
            keys.append(k)

    if not keys:
        return "(empty)"

    lines: list[str] = []
    for k in keys:
        lines.append(f"{k}: {w.get(k)}")
    return "\n".join(lines)


def build_router_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Router builds the plan:
      - intent
      - constraints
      - language

      - ready (whether to proceed to answer/codegen now)
      - need_chat_history + chat_history_k
      - retrieval_k + memory_query
      - world_view ("none" | "full") for persistent snapshot only

    Time is ALWAYS available via state["world"]["now"] / ["tz"].
    """
    if "router" not in deps.models:
        raise RuntimeError("config: llm.langgraph_nodes.router is required for router node")

    model = deps.models["router"]
    user_input = state["task"]["user_input"]

    capabilities = (
        "[CAPABILITIES]\n"
        "- chat_history: can fetch last N chat turns from local history file.\n"
        "- memory_retrieval: can fetch top-K relevant memories from OpenMemory.\n"
        "- world_snapshot: can fetch persistent world state (topics/goals/project).\n"
        "- time: now/tz are always available (no fetch required).\n"
    )

    w = state.get("world") or {}
    now = str(w.get("now", "") or "")
    tz = str(w.get("tz", "") or "")

    prompt = deps.prompt_loader.render(
        "router",
        user_input=user_input,
        capabilities=capabilities,
        now=now,
        tz=tz,
        chat_history=_render_chat_history(state),
        memories_summary=_render_memories_summary(state),
        world_summary=_render_world_summary(state),
    )
    return model, prompt
