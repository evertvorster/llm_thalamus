from __future__ import annotations

from typing import List

from orchestrator.deps import Deps
from orchestrator.state import State


def _parse_bullets_by_section(text: str) -> List[str]:
    """
    Parse reflection output into individual memory strings.

    Rules:
    - Section headers (EPISODIC / SEMANTIC / etc.) are ignored
    - Each bullet becomes ONE memory
    - Multi-line bullets stay together
    """
    memories: List[str] = []

    current: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            continue

        # Section headers (instructional only)
        if line.strip().upper().endswith(":"):
            if current:
                memories.append("\n".join(current).strip())
                current = []
            continue

        # Bullet start
        if line.lstrip().startswith("- "):
            if current:
                memories.append("\n".join(current).strip())
                current = []
            current.append(line.lstrip()[2:])
        else:
            # Continuation of previous bullet
            if current:
                current.append(line.strip())

    if current:
        memories.append("\n".join(current).strip())

    return [m for m in memories if m]


def run_reflect_store_node(state: State, deps: Deps) -> None:
    """
    Post-turn reflection + memory storage.

    Side effects only:
    - Calls OpenMemory add_memory() once per extracted memory
    """
    model = deps.models.get("agent")
    if not model:
        raise RuntimeError("No model configured for reflection (expected 'agent')")

    user_msg = state["task"]["user_input"]
    answer = state["final"]["answer"]

    prompt = deps.prompt_loader.render(
        "reflect_store",
        user_message=user_msg,
        assistant_message=answer,
    )

    response_parts: List[str] = []

    for kind, text in deps.llm_generate_stream(model, prompt):
        if kind == "response" and text:
            response_parts.append(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return

    memories = _parse_bullets_by_section(reflection_text)
    if not memories:
        return

    client = deps.openmemory_client
    if client is None:
        raise RuntimeError("OpenMemory client not initialized")

    from thalamus_openmemory.api import add_memory

    for mem in memories:
        add_memory(
            client,
            mem,
            user_id=deps.cfg.default_user_id,
        )

    state["runtime"]["node_trace"].append(f"reflect_store:{len(memories)}")
