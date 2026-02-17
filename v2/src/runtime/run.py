from __future__ import annotations

from orchestrator.deps import build_deps
from orchestrator.state import new_state_for_turn
from config import bootstrap_config

from runtime.build import run_graph


def emit(ev) -> None:
    # Your old UI expects dict Events; this prints them for the harness.
    # (If your runtime emits Event dataclasses anywhere, just str() them here.)
    print(ev)


if __name__ == "__main__":
    # Bootstrap config exactly like the real app
    cfg = bootstrap_config(["--dev"])

    # For this harness, we don't need OpenMemory; pass None.
    deps = build_deps(cfg, openmemory_client=None)

    # Make a real orchestrator State
    state = new_state_for_turn(
        turn_id="runtime-smoke",
        user_input="Hello from the new runtime graph.",
        turn_seq=1,
    )

    # Run the 2-node graph
    out = run_graph(state, deps, emit)

    print("\nassistant_text:\n", out["final"].get("answer", ""))
