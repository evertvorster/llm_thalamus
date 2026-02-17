# orchestrator/nodes/<group>_<name>.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

from orchestrator.deps import Deps
from orchestrator.state import State


# ---- Node metadata (used later for registry / UI / manifest) ----

NODE_ID = "<group>.<name>"          # e.g. "llm.answer" or "mech.build_context"
NODE_GROUP = "<group>"              # e.g. "llm" | "mech" | "tool"
NODE_LABEL = "<Human label>"        # e.g. "Answer", "Build Context"
PROMPT_REF: Optional[str] = "resources/prompts/<name>.txt"   # set None for mech/tool nodes


@dataclass(frozen=True)
class NodeResult:
    """
    Return a small, explicit delta. Keep it narrow.
    """
    # You can evolve this into a standard "delta" shape later.
    state: State


def _emit(emit, *, phase: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Minimal event helper. Avoid fancy logic here; keep shared code small.
    """
    payload = {
        "type": "node_event",
        "node_id": NODE_ID,
        "group": NODE_GROUP,
        "phase": phase,     # "start" | "end" | "error" | "progress"
        "msg": msg,
    }
    if data:
        payload["data"] = data
    emit(payload)


def _render_prompt(template: str, mapping: Dict[str, str]) -> str:
    """
    Deterministic substitution using <<TOKENS>>.
    Fail-fast if any token remains.
    """
    prompt = template
    for k, v in mapping.items():
        prompt = prompt.replace(f"<<{k}>>", v)

    # Fail if unresolved tokens remain.
    import re
    leftover = re.findall(r"<<[A-Z0-9_]+>>", prompt)
    if leftover:
        raise RuntimeError(f"Unresolved prompt tokens: {sorted(set(leftover))}")

    return prompt


def make_node_<name>(deps: Deps, emit) -> Callable[[State], State]:
    """
    Factory called by graph_build.py: g.add_node("<graph_name>", make_node_<name>(deps, emit))
    Keep this wrapper thin and deterministic.
    """

    # Load prompt template if this is an LLM node.
    template: Optional[str] = None
    if PROMPT_REF:
        # IMPORTANT: replace this with your existing prompt loading mechanism.
        # e.g. deps.prompts.load_text(PROMPT_REF) or Path(PROMPT_REF).read_text()
        template = deps.prompts.load_text(PROMPT_REF)  # <-- adjust to your actual API

    def _node(state: State) -> State:
        _emit(emit, phase="start", msg=f"Running {NODE_ID}")

        try:
            # ---- Example: assemble inputs (keep it small & explicit) ----
            user_text = state.user_text  # <-- adjust to your State shape
            world_json = state.world_view_json  # <-- adjust
            memories = state.memories_text  # <-- adjust

            # ---- If this is an LLM node, render prompt and call model ----
            if template is not None:
                prompt = _render_prompt(
                    template,
                    {
                        "USER_MESSAGE": user_text,
                        "WORLD_STATE_JSON": world_json,
                        "RETRIEVED_MEMORIES": memories,
                    },
                )

                # IMPORTANT: call your LLM via deps (adjust to your actual API).
                # Keep outputs strictly separated: ops events vs thinking events.
                #
                # Example (placeholder):
                #   result = deps.llm.generate(prompt, emit_thought=lambda t: emit({...}))
                #   assistant_text = result.text
                assistant_text = deps.llm.generate_text(prompt)  # <-- adjust

                # Write result into state in ONE place (avoid scattered keys).
                state.assistant_text = assistant_text  # <-- adjust to your state mutation style

            else:
                # ---- Mech/tool node work goes here ----
                # Do deterministic work and store output in a narrow state key.
                pass

            _emit(emit, phase="end", msg=f"Done {NODE_ID}")
            return state

        except Exception as e:
            _emit(emit, phase="error", msg=f"Failed {NODE_ID}", data={"error": str(e)})
            raise

    return _node
