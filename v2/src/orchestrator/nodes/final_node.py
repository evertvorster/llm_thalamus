from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


_TIME_KEYWORDS = (
    "time",
    "date",
    "today",
    "yesterday",
    "tomorrow",
    "tonight",
    "this morning",
    "this afternoon",
    "this evening",
    "last week",
    "next week",
    "last month",
    "next month",
    "last year",
    "next year",
    "now",
    "current time",
    "current date",
)


def _should_inject_world(*, user_input: str, intent: str) -> bool:
    # Planning/logistics benefit from a stable 'now' reference.
    if intent == "planning":
        return True

    s = user_input.lower()
    return any(k in s for k in _TIME_KEYWORDS)


def _render_world_block(state: State) -> str:
    w = state.get("world") or {}
    if not isinstance(w, dict) or not w:
        return ""

    # Minimal, stable rendering. Avoid dumping JSON.
    lines: list[str] = ["[WORLD]"]

    now = w.get("now")
    tz = w.get("tz")
    if now:
        lines.append(f"now: {now}")
    if tz:
        lines.append(f"tz: {tz}")

    space = w.get("space")
    if space:
        lines.append(f"space: {space}")

    topics = w.get("topics") or []
    if isinstance(topics, list) and topics:
        lines.append(f"topics: {topics}")

    goals = w.get("goals") or []
    if isinstance(goals, list) and goals:
        lines.append(f"goals: {goals}")

    return "\n".join(lines) + "\n"


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Final node logic:
      - pick the configured final model
      - build the prompt from resources/prompts/final.txt
      - optionally include retrieval context (if any)
      - optionally include a world block (time/space) when relevant

    NOTE:
      Retrieval memories may include an ISO 8601 timestamp on `m["ts"]`.
      We render this in simple English as: "<text>" created at <ts>.
    """
    model = deps.models["final"]
    user_input = state["task"]["user_input"]
    intent = state.get("task", {}).get("intent") or ""

    memories = state.get("context", {}).get("memories", [])
    context = ""
    if memories:
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

        context = "\n" + "\n".join(lines) + "\n"

    world = _render_world_block(state) if _should_inject_world(user_input=user_input, intent=intent) else ""

    prompt = deps.prompt_loader.render(
        "final",
        user_input=user_input,
        context=context,
        world=world,
    )
    return model, prompt
