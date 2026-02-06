from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Final node logic:
      - pick the configured final model
      - build the prompt from resources/prompts/final.txt
      - optionally include retrieval context (if any)

    NOTE:
      Retrieval memories may include an ISO 8601 timestamp on `m["ts"]`.
      We render this in simple English as: "<text>" created at <ts>.
    """
    model = deps.models["final"]
    user_input = state["task"]["user_input"]

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
                # Human-friendly, simple English
                lines.append(f'- "{text}" created at {ts}')
            else:
                # Backwards-compatible rendering
                lines.append(f"- {text}")

        context = "\n" + "\n".join(lines) + "\n"

    prompt = deps.prompt_loader.render("final", user_input=user_input, context=context)
    return model, prompt
