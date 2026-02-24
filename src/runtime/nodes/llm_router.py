from __future__ import annotations

import json
from typing import Any, Callable

from runtime.deps import Deps
from runtime.emitter import TurnEmitter
from runtime.prompting import render_tokens
from runtime.providers.types import Message
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.tool_loop import chat_stream


NODE_ID = "llm.router"
GROUP = "llm"
LABEL = "Router"
PROMPT_NAME = "runtime_router"  # resources/prompts/runtime_router.txt


def _get_emitter(state: State) -> TurnEmitter:
    em = state.get("runtime", {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _topic_query_from_world(world: dict[str, Any]) -> str:
    # Deterministic, small, and stable: cap topics and include project if present.
    topics = world.get("topics")
    if not isinstance(topics, list):
        topics = []

    parts: list[str] = []

    project = world.get("project")
    if isinstance(project, str) and project.strip():
        parts.append(project.strip())

    for t in topics[:8]:
        if isinstance(t, str) and t.strip():
            parts.append(t.strip())

    # Fallback: if nothing is available, return empty string (caller should skip).
    return " | ".join(parts).strip()


def _prefill_context_sources(
    *,
    state: State,
    services: RuntimeServices,
    emitter: TurnEmitter,
) -> None:
    """Mechanically add a couple of chat turns and a handful of memories to context.

    This reuses the same ToolSet handlers as the tool loop (no parallel tool logic).
    Failures are non-fatal and should not break routing.
    """

    ctx = state.setdefault("context", {})
    sources = ctx.setdefault("sources", [])
    if not isinstance(sources, list):
        # If an upstream prompt produced a non-list, don't try to repair it here.
        return

    toolset = services.tools.toolset_for_node("router")

    # 1) Recent chat turns
    try:
        h = toolset.handlers.get("chat_history_tail")
        if h is not None:
            raw = h(json.dumps({"limit": 2}, ensure_ascii=False))
            obj = _safe_json_loads(raw)
            if isinstance(obj, dict):
                sources.append(obj)
                emitter.emit(
                    emitter.factory.log_line(
                        level="info",
                        logger="router",
                        message="[prefill] added chat_history_tail source to context.sources",
                        node_id=NODE_ID,
                        fields={"limit": 4},
                    )
                )
    except Exception as e:
        emitter.emit(
            emitter.factory.log_line(
                level="warning",
                logger="router",
                message=f"[prefill] chat_history_tail failed: {e}",
                node_id=NODE_ID,
            )
        )

    # 2) Memory search based on world topics
    try:
        h = toolset.handlers.get("memory_query")
        if h is not None:
            world = state.get("world") or {}
            if isinstance(world, dict):
                query = _topic_query_from_world(world)
            else:
                query = ""

            if query:
                raw = h(
                    json.dumps(
                        {
                            "query": query,
                            "type": "contextual",
                            "k": 7,
                        },
                        ensure_ascii=False,
                    )
                )
                obj = _safe_json_loads(raw)
                if isinstance(obj, dict):
                    sources.append(obj)
                    emitter.emit(
                        emitter.factory.log_line(
                            level="info",
                            logger="router",
                            message="[prefill] added memory_query source to context.sources",
                            node_id=NODE_ID,
                            fields={"k": 5, "type": "contextual", "query": query},
                        )
                    )
    except Exception as e:
        emitter.emit(
            emitter.factory.log_line(
                level="warning",
                logger="router",
                message=f"[prefill] memory_query failed: {e}",
                node_id=NODE_ID,
            )
        )


def make(deps: Deps, services: RuntimeServices | None = None) -> Callable[[State], State]:
    if services is None:
        raise RuntimeError("llm.router requires RuntimeServices (for mechanical prefill)")

    template = deps.load_prompt(PROMPT_NAME)

    def node(state: State) -> State:
        state.setdefault("runtime", {}).setdefault("node_trace", []).append(NODE_ID)
        emitter = _get_emitter(state)

        span = emitter.span(node_id=NODE_ID, label=LABEL)

        try:
            # Mechanical prefill (chat tail + memory query) before the router LLM runs.
            _prefill_context_sources(state=state, services=services, emitter=emitter)

            user_text = str(state.get("task", {}).get("user_text", "") or "")
            now = str(state.get("runtime", {}).get("now_iso", "") or "")
            tz = str(state.get("runtime", {}).get("timezone", "") or "")

            world_json = json.dumps(
                state.get("world", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )

            prompt = render_tokens(
                template,
                {
                    "USER_MESSAGE": user_text,
                    "NOW": now,
                    "TZ": tz,
                    "WORLD_JSON": world_json,
                },
            )

            raw_parts: list[str] = []

            for ev in chat_stream(
                provider=deps.provider,
                model=deps.get_llm("router").model,
                messages=[Message(role="user", content=prompt)],
                params=deps.get_llm("router").params,
                response_format=deps.get_llm("router").response_format,
                tools=None,  # router is structured; tools are disabled here
                max_steps=deps.tool_step_limit,
            ):
                if ev.type == "delta_text" and ev.text:
                    # Router output is structured JSON; do NOT treat as "thinking".
                    raw_parts.append(ev.text)

                elif ev.type == "delta_thinking" and ev.text:
                    # Only actual model thinking goes to the thinking log.
                    span.thinking(ev.text)

                elif ev.type == "error":
                    raise RuntimeError(ev.error or "LLM provider error")

                elif ev.type == "done":
                    break

            raw_text = "".join(raw_parts).strip()
            obj = json.loads(raw_text)
            if not isinstance(obj, dict):
                raise RuntimeError("router: output must be a JSON object")

            route = str(obj.get("route", "answer") or "answer").strip() or "answer"
            language = str(obj.get("language", "en") or "en").strip() or "en"
            status = str(obj.get("status", "") or "").strip()

            state.setdefault("task", {})["language"] = language
            state.setdefault("task", {})["route"] = route  # <-- critical for branching
            state.setdefault("runtime", {})["status"] = status

            span.end_ok()
            return state

        except Exception as e:
            span.end_error(code="NODE_ERROR", message=str(e))
            raise

    return node


register(
    NodeSpec(
        node_id=NODE_ID,
        group=GROUP,
        label=LABEL,
        role="router",
        make=make,
        prompt_name=PROMPT_NAME,
    )
)
