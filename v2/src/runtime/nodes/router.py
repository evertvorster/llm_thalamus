from __future__ import annotations

import json
import uuid
from typing import Callable, Dict

from runtime.deps import Deps
from runtime.events import emit_ops, emit_thought
from runtime.prompt_loader import load_prompt_text
from runtime.registry import NodeSpec, register
from runtime.state import State

NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_REF = "router.txt"


def _render(template: str, mapping: Dict[str, str]) -> str:
    prompt = template
    for k, v in mapping.items():
        prompt = prompt.replace(f"<<{k}>>", v)

    # Fail fast on unresolved tokens
    import re
    leftover = re.findall(r"<<[A-Z0-9_]+>>", prompt)
    if leftover:
        raise RuntimeError(f"Unresolved prompt tokens: {sorted(set(leftover))}")
    return prompt


def make(deps: Deps, emit) -> Callable[[State], State]:
    template = load_prompt_text(deps.prompt_root, PROMPT_REF)

    def node(state: State) -> State:
        run_id = state.scratch.get("run_id") or str(uuid.uuid4())
        state.scratch["run_id"] = run_id
        span_id = str(uuid.uuid4())

        emit_ops(emit, run_id=run_id, span_id=span_id, node_id=NODE_ID, phase="start", msg="Routing")

        try:
            prompt = _render(template, {"USER_MESSAGE": state.user_text})

            def _thought_cb(t: str) -> None:
                emit_thought(emit, run_id=run_id, span_id=span_id, node_id=NODE_ID, text=t)

            raw = deps.llm.complete_json(prompt, emit_thought=_thought_cb)

            # Strict JSON parse (router must be deterministic)
            obj = json.loads(raw)

            route = obj.get("route")
            conf = obj.get("confidence")

            if route not in ("answer",):
                raise RuntimeError(f"Invalid route from router: {route!r}")
            if conf not in ("low", "medium", "high"):
                raise RuntimeError(f"Invalid confidence from router: {conf!r}")

            state.route = route
            state.route_confidence = conf

            emit_ops(
                emit,
                run_id=run_id,
                span_id=span_id,
                node_id=NODE_ID,
                phase="end",
                msg="Routing decided",
                data={"route": route, "confidence": conf},
            )
            return state

        except Exception as e:
            emit_ops(emit, run_id=run_id, span_id=span_id, node_id=NODE_ID, phase="error", msg="Router failed", data={"error": str(e)})
            raise

    return node


register(NodeSpec(node_id=NODE_ID, group=GROUP, label=LABEL, make=make, prompt_ref=PROMPT_REF))
