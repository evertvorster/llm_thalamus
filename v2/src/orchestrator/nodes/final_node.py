from __future__ import annotations

from orchestrator.deps import Deps
from orchestrator.state import State


def build_final_request(state: State, deps: Deps) -> tuple[str, str]:
    """
    Final node logic:
      - pick the configured final model
      - build the prompt from resources/prompts/final.txt
      - optionally include retrieval context (if any)
    """
    model = deps.models["final"]
    user_input = state["task"]["user_input"]

    memories = state.get("context", {}).get("memories", [])
    context = ""
    if memories:
        lines = ["Context:"]
        for m in memories:
            text = str(m.get("text", "")).strip()
            if text:
                lines.append(f"- {text}")
        context = "\n" + "\n".join(lines) + "\n"

    prompt = deps.prompt_loader.render("final", user_input=user_input, context=context)
    return model, prompt
