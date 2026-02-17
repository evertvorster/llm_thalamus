from __future__ import annotations

from typing import Callable

from orchestrator.deps import Deps
from orchestrator.state import State

from runtime.graph_nodes import collect_streamed_response
from runtime.json_extract import extract_first_json_object
from runtime.prompting import render_tokens
from runtime.registry import NodeSpec, register


NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_NAME = "runtime_router"  # resources/prompts/runtime_router.txt


def make(deps: Deps) -> Callable[[State], State]:
    template = deps.prompt_loader.load(PROMPT_NAME)  # PromptLoader already anchors resources_root/prompts. :contentReference[oaicite:7]{index=7}
    model = deps.models.get("router") or deps.models.get("final")  # keep bootstrap tolerant

    def node(state: State) -> State:
        # Record trace
        state["runtime"]["node_trace"].append(NODE_ID)

        prompt = render_tokens(
            template,
            {
                "USER_MESSAGE": state["task"]["user_input"],
                "NOW": str(state["world"].get("now", "")),
                "TZ": str(state["world"].get("tz", "")),
            },
        )

        # Stream from Ollama and collect response body (while emitting logs upstream)
        stream = deps.llm_generate_stream(model, prompt)

        def _on_chunk(t: str) -> None:
            # graph_runner wraps this and emits as Event(type="log")
            state.setdefault("_runtime_logs", []).append(t)  # local scratch (runner reads+clears)

        raw = collect_streamed_response(stream, on_chunk=_on_chunk)

        obj = extract_first_json_object(raw)
        route = str(obj.get("route", "") or "").strip()
        language = str(obj.get("language", "") or "en").strip() or "en"
        status = str(obj.get("status", "") or "").strip()

        # Bootstrap: only "answer" is valid. (Later you’ll extend to planner/tool paths.)
        if route not in ("answer",):
            raise RuntimeError(f"router returned invalid route={route!r}")

        # Preserve old semantics: router can set plan_mode; keep it "direct" in bootstrap.
        state["task"]["plan_mode"] = "direct"
        state["task"]["language"] = language
        state["runtime"]["status"] = status

        # Store route decision for graph policy
        state.setdefault("_next_node", "answer")
        return state

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
