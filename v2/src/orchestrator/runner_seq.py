from __future__ import annotations

import json
from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.codegen_node import run_codegen_stub
from orchestrator.nodes.final_node import build_final_request
from orchestrator.nodes.retrieval_node import run_retrieval_node
from orchestrator.nodes.router_node import build_router_request
from orchestrator.state import State


_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}


def _extract_json_object(text: str) -> str:
    """Extract the first JSON object from a string."""
    s = text.strip()
    if not s:
        raise ValueError("router: empty output")

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"router: output does not contain a JSON object: {s!r}")

    return s[start : end + 1]


def _parse_router_json(text: str) -> tuple[str, list[str], str]:
    raw_json = _extract_json_object(text)
    try:
        obj = json.loads(raw_json)
    except Exception as e:
        raise ValueError(f"router: invalid JSON: {raw_json!r}") from e

    if not isinstance(obj, dict):
        raise ValueError("router: JSON must be an object")

    # ---- intent (soft defaults) ----
    intent = obj.get("intent")
    if not isinstance(intent, str) or not intent.strip():
        intent = "qa"
    else:
        intent = intent.strip()

    if intent not in _ALLOWED_INTENTS:
        intent = "qa"

    # ---- constraints ----
    constraints_obj = obj.get("constraints", [])
    if constraints_obj is None:
        constraints_obj = []
    if not isinstance(constraints_obj, list):
        raise ValueError("router: constraints must be an array")

    constraints: list[str] = []
    for c in constraints_obj:
        if c is None:
            continue
        constraints.append(str(c).strip())

    # ---- language ----
    language = obj.get("language", "")
    if language is None:
        language = ""
    if not isinstance(language, str):
        language = str(language)
    language = language.strip()

    return intent, constraints, language


def run_turn_seq(state: State, deps: Deps) -> Iterator[Event]:
    """
    Sequential runner (pre-LangGraph).

    Pipeline:
      router
        -> retrieval (research/ops)
        -> codegen stub (coding)
        -> final

    Only `final` produces UI-consumed output.
    """

    # =========================
    # Router
    # =========================
    yield {"type": "node_start", "node": "router"}

    router_model, router_prompt = build_router_request(state, deps)

    router_response_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(router_model, router_prompt):
        if not text:
            continue

        # show all streamed text in the thinking panel
        yield {"type": "log", "text": text}

        if kind == "response":
            router_response_parts.append(text)

    router_text = "".join(router_response_parts).strip()
    intent, constraints, language = _parse_router_json(router_text)

    state["task"]["intent"] = intent
    state["task"]["constraints"] = constraints
    state["task"]["language"] = language
    state["runtime"]["node_trace"].append(f"router:intent={intent}")

    yield {"type": "node_end", "node": "router"}

    # =========================
    # Branching
    # =========================
    if intent in {"research", "ops"}:
        # caller can override state["task"]["retrieval_k"] elsewhere;
        # None means "use config default"
        state["task"]["retrieval_k"] = None
        yield {"type": "node_start", "node": "retrieval"}
        state = run_retrieval_node(state, deps)
        state["runtime"]["node_trace"].append("retrieval:openmemory")
        yield {"type": "node_end", "node": "retrieval"}

    elif intent == "coding":
        yield {"type": "node_start", "node": "codegen"}
        state = run_codegen_stub(state, deps)
        yield {"type": "node_end", "node": "codegen"}

    elif intent == "planning":
        # planner not implemented yet
        state["runtime"]["node_trace"].append("planning:fallthrough")

    # =========================
    # Final
    # =========================
    yield {"type": "node_start", "node": "final"}

    final_model, final_prompt = build_final_request(state, deps)

    response_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(final_model, final_prompt):
        if not text:
            continue

        # stream thinking/log output
        yield {"type": "log", "text": text}

        if kind == "response":
            response_parts.append(text)

    answer = "".join(response_parts).strip()
    state["final"]["answer"] = answer
    state["runtime"]["node_trace"].append("final:ollama")

    yield {"type": "node_end", "node": "final"}
    yield {"type": "final", "answer": answer}
