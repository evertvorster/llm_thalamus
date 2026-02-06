from __future__ import annotations

import json
from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.nodes.final_node import build_final_request
from orchestrator.nodes.router_node import build_router_request
from orchestrator.state import State


_ALLOWED_INTENTS = {"qa", "coding", "planning", "research", "ops"}


def _extract_json_object(text: str) -> str:
    """
    Extract the first JSON object from a string.
    Keeps logic explicit and failure modes loud.
    """
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

    intent = obj.get("intent", "")
    if not isinstance(intent, str) or intent.strip() == "":
        raise ValueError("router: intent must be a non-empty string")
    intent = intent.strip()

    # soft-fail: if the model returns an unknown intent like "other",
    # map it to a safe default instead of killing the whole turn.
    if intent not in _ALLOWED_INTENTS:
        intent = "qa"


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

    Now runs:
      router -> final

    Router is strict JSON-only and updates task intent/constraints/language.
    """
    # ---- router ----
    yield {"type": "node_start", "node": "router"}

    router_model, router_prompt = build_router_request(state, deps)

    router_response_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(router_model, router_prompt):
        if not text:
            continue

        # always stream to thinking panel
        yield {"type": "log", "text": text}

        # only response is parsed
        if kind == "response":
            router_response_parts.append(text)

    router_text = "".join(router_response_parts).strip()
    raw_router_text = router_text
    intent, constraints, language = _parse_router_json(router_text)

    state["task"]["intent"] = intent
    state["task"]["constraints"] = constraints
    state["task"]["language"] = language
    state["runtime"]["node_trace"].append(f"router:intent={intent}")

    yield {"type": "node_end", "node": "router"}

    # ---- final ----
    yield {"type": "node_start", "node": "final"}

    final_model, final_prompt = build_final_request(state, deps)

    response_parts: list[str] = []

    for kind, text in deps.llm_generate_stream(final_model, final_prompt):
        if not text:
            continue

        # Always show live progress in the thinking panel.
        yield {"type": "log", "text": text}

        # Only user-facing response becomes the final answer.
        if kind == "response":
            response_parts.append(text)

    answer = "".join(response_parts).strip()
    state["final"]["answer"] = answer
    state["runtime"]["node_trace"].append("final:ollama")

    yield {"type": "node_end", "node": "final"}
    yield {"type": "final", "answer": answer}
