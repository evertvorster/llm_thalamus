from __future__ import annotations

from typing import Callable, List, Optional

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


def run_reflect_store_node(
    state: State,
    deps: Deps,
    *,
    on_delta: Optional[Callable[[str], None]] = None,
    on_memory_saved: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Post-turn reflection + memory storage.

    Side effects only:
    - Calls deps.openmemory.add() once per extracted memory

    Optional callbacks:
      - on_delta: streamed LLM output (thinking + response chunks)
      - on_memory_saved: called once per stored memory with the exact text stored
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
        if not text:
            continue

        # Forward both thinking + response to the UI
        if on_delta is not None:
            on_delta(text)

        # Only response tokens are used to build the reflection text for parsing
        if kind == "response":
            response_parts.append(text)

    reflection_text = "".join(response_parts).strip()
    if not reflection_text:
        return

    memories = _parse_bullets_by_section(reflection_text)
    if not memories:
        return

    for mem in memories:
        deps.openmemory.add(mem)
        if on_memory_saved is not None:
            on_memory_saved(mem)

    state["runtime"]["node_trace"].append(f"reflect_store:{len(memories)}")
