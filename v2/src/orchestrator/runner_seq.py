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
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in router output")

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise ValueError("unterminated JSON object in router output")


def _parse_router_output(raw: str) -> dict:
    blob = _extract_json_object(raw)
    data = json.loads(blob)

    intent = (data.get("intent") or "").strip().lower()
    if not intent or intent not in _ALLOWED_INTENTS:
        intent = "qa"

    constraints = data.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []

    language = (data.get("language") or "").strip().lower() or "en"

    return {"intent": intent, "constraints": constraints, "language": language}


def run_turn_seq(state: State, deps: Deps) -> Iterator[Event]:
    # =========================
    # Router
    # =========================
    yield {"type": "node_start", "node": "router"}

    router_model, router_prompt = build_router_request(state, deps)

    router_chunks: list[str] = []
    for kind, text in deps.llm_generate_stream(router_model, router_prompt):
        if not text:
            continue
        if kind == "response":
            router_chunks.append(text)
            yield {"type": "log", "text": text}
        else:
            # still forward "thinking" in logs for visibility
            yield {"type": "log", "text": text}

    yield {"type": "node_end", "node": "router"}

    router_raw = "".join(router_chunks).strip()
    parsed = _parse_router_output(router_raw)

    state["task"]["intent"] = parsed["intent"]
    state["task"]["constraints"] = parsed["constraints"]
    state["task"]["language"] = parsed["language"]

    intent = state["task"]["intent"]

    # =========================
    # Branching
    # =========================
    # Retrieval policy:
    # - Always run for research/ops
    # - Also run for any intent if default_k > 0 (default memory-aware behavior)
    default_k = int(deps.cfg.orchestrator_retrieval_default_k)
    want_retrieval = (intent in {"research", "ops"}) or (default_k > 0)

    if want_retrieval:
        # caller can override state["task"]["retrieval_k"] elsewhere;
        # None means "use config default"
        state["task"]["retrieval_k"] = None
        yield {"type": "node_start", "node": "retrieval"}
        state = run_retrieval_node(state, deps)

        mems = state.get("context", {}).get("memories", [])
        yield {"type": "log", "text": f"\n[retrieval] memories={len(mems)}\n"}
        for m in mems[:3]:
            txt = str(m.get("text", "") or "")
            yield {"type": "log", "text": f"- {txt[:200]}\n"}

        state["runtime"]["node_trace"].append("retrieval:openmemory")
        yield {"type": "node_end", "node": "retrieval"}

    if intent == "coding":
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

    answer_parts: list[str] = []
    for kind, text in deps.llm_generate_stream(final_model, final_prompt):
        if not text:
            continue
        if kind == "response":
            answer_parts.append(text)
            yield {"type": "log", "text": text}
        else:
            yield {"type": "log", "text": text}

    yield {"type": "node_end", "node": "final"}

    answer = "".join(answer_parts).strip()
    state["final"]["answer"] = answer

    yield {"type": "final", "answer": answer}
