from __future__ import annotations

from pathlib import Path
from typing import Callable, Tuple

from orchestrator.deps import Deps
from orchestrator.episodic_retrieval import (
    derive_episodes_db_path,
    execute_select,
    validate_select_sql,
)
from orchestrator.events import Event
from orchestrator.nodes.router_node import (
    _render_chat_history,
    _render_memories_summary,
    _render_world_summary,
)
from orchestrator.state import State


# Internal loop controls (MVP defaults; can be moved to config later)
_MAX_EPISODE_ROUNDS = 8
_MAX_SQL_REJECTIONS = 3

_MAX_ROWS = 50
_MAX_CHARS = 12_000
_FIELD_TRIM = 600


def _append_status(state: State, msg: str) -> None:
    msg = (msg or "").strip()
    if not msg:
        return
    cur = (state.get("runtime", {}).get("status") or "").strip()
    if not cur:
        state["runtime"]["status"] = msg
    else:
        # Keep as one string channel; append with newline separator.
        state["runtime"]["status"] = cur + "\n" + msg


def _collect_llm_response(
    deps: Deps,
    *,
    model: str,
    prompt: str,
    emit: Callable[[Event], None],
) -> str:
    parts: list[str] = []
    for kind, text in deps.llm_generate_stream(model, prompt):
        if not text:
            continue
        emit({"type": "log", "text": text})
        if kind == "response":
            parts.append(text)
    return "".join(parts).strip()


def _choose_models(deps: Deps) -> Tuple[str, str]:
    """
    Allow dedicated models if present; otherwise reuse router/final.
    """
    sql_model = deps.models.get("episode_sql") or deps.models.get("router")
    sum_model = deps.models.get("episode_summarize") or deps.models.get("final")
    if not sql_model:
        # Fallback to final if router is missing (should not happen in your config).
        sql_model = deps.models.get("final", "")
    if not sum_model:
        sum_model = deps.models.get("router", "") or deps.models.get("final", "")
    return str(sql_model), str(sum_model)


def _episodes_schema_block() -> str:
    return (
        "[EPISODES DB CATALOG (SQLite)]\n"
        "Available tables (complete list):\n"
        "- episodes\n"
        "\n"
        "You must ONLY query the episodes table.\n"
        "Do NOT query sqlite_master or PRAGMA in generated SQL.\n"
        "\n"
        "[episodes columns]\n"
        "id INTEGER PRIMARY KEY\n"
        "ts_utc TEXT (NOT NULL)\n"
        "ts_local TEXT (NOT NULL)  -- ISO8601 string; lexicographic compare works\n"
        "turn_id TEXT (NOT NULL)\n"
        "turn_seq INTEGER (NOT NULL)\n"
        "intent TEXT\n"
        "world_view TEXT\n"
        "retrieval_k INTEGER\n"
        "updated_at TEXT\n"
        "project TEXT\n"
        "topics_json TEXT\n"
        "goals_json TEXT\n"
        "rules_json TEXT\n"
        "identity_user_name TEXT\n"
        "identity_session_user_name TEXT\n"
        "identity_agent_name TEXT\n"
        "identity_user_location TEXT\n"
        "user_text TEXT (NOT NULL)\n"
        "assistant_text TEXT (NOT NULL)\n"
        "world_before_json TEXT\n"
        "world_after_json TEXT\n"
        "world_delta_json TEXT\n"
        "memories_saved_json TEXT\n"
        "\n"
        "Query patterns:\n"
        "- time windows: WHERE ts_local >= 'YYYY-..' AND ts_local < 'YYYY-..'\n"
        "- aggregates for long spans: COUNT(*) GROUP BY project/intent\n"
        "- avoid selecting JSON/text blobs unless needed (user_text/assistant_text already large)\n"
        "- always include LIMIT\n"
    )



def run_episode_query_node(
    state: State,
    deps: Deps,
    *,
    emit: Callable[[Event], None],
) -> State:
    """
    Episodic retrieval node:
      - LLM #1 authors SQL (SELECT-only)
      - validate SQL mechanically (hard gate)
      - execute with strict budgets (rows/chars/field trim)
      - LLM #2 either FINAL summarizes or requests REFINE
      - loops internally up to _MAX_EPISODE_ROUNDS
      - writes results into state.context.episodes_summary / episodes_hits
      - uses state.runtime.status as the router->final diagnostic channel
    """
    # If already have a summary, treat as done.
    if (state.get("context", {}).get("episodes_summary") or "").strip():
        state["task"]["need_episodes"] = False
        return state

    sql_model, sum_model = _choose_models(deps)

    # Derive DB path (episodes.sqlite next to OpenMemory DB)
    db_path: Path = derive_episodes_db_path(openmemory_db_path=str(deps.cfg.openmemory_db_path))

    # Build the "router-equivalent" context blocks (parity guarantee)
    w = state.get("world") or {}
    now = str(w.get("now", "") or "")
    tz = str(w.get("tz", "") or "")

    user_input = state["task"]["user_input"]
    chat_history = _render_chat_history(state)
    memories_summary = _render_memories_summary(state)
    world_summary = _render_world_summary(state)

    base_status = (state.get("runtime", {}).get("status") or "").strip()

    # Loop control
    last_sql = ""
    last_meta_text = ""
    sql_rejections = 0

    for round_idx in range(1, _MAX_EPISODE_ROUNDS + 1):
        emit({"type": "log", "text": f"\n[episode_query] round {round_idx}/{_MAX_EPISODE_ROUNDS}\n"})

        # --- LLM #1: SQL author ---
        prompt_sql = deps.prompt_loader.render(
            "episode_sql_query",
            user_input=user_input,
            now=now,
            tz=tz,
            chat_history=chat_history,
            memories_summary=memories_summary,
            world_summary=world_summary,
            status=base_status if base_status else "(empty)",
            schema=_episodes_schema_block(),
            last_sql=last_sql if last_sql else "(none)",
            last_meta=last_meta_text if last_meta_text else "(none)",
        )

        sql_text = _collect_llm_response(deps, model=sql_model, prompt=prompt_sql, emit=emit)

        # Normalize “code fence” accidents
        sql_text = sql_text.strip()
        if sql_text.startswith("```"):
            sql_text = sql_text.strip("`").strip()
        # Keep only the first line if model rambles
        if "\n" in sql_text:
            # Some models return explanations; we only want the first plausible SQL line.
            first = sql_text.splitlines()[0].strip()
            if first:
                sql_text = first

        last_sql = sql_text
        emit({"type": "log", "text": f"\n[episode_query] sql_candidate:\n{sql_text}\n"})

        ok, reason = validate_select_sql(sql_text)
        if not ok:
            sql_rejections += 1
            _append_status(state, f"Episodic SQL rejected: {reason}")
            emit({"type": "log", "text": f"\n[episode_query] SQL rejected: {reason}\n"})
            last_meta_text = f"SQL rejected: {reason}"
            if sql_rejections >= _MAX_SQL_REJECTIONS:
                _append_status(state, "Episodic retrieval failed: too many invalid SQL attempts.")
                state["task"]["need_episodes"] = False
                return state
            continue

        # --- Execute with hard budgets ---
        try:
            rows, meta = execute_select(
                db_path=db_path,
                sql=sql_text,
                max_rows=_MAX_ROWS,
                max_chars=_MAX_CHARS,
                field_trim=_FIELD_TRIM,
            )
        except Exception as e:
            _append_status(state, f"Episodic DB query failed: {e}")
            emit({"type": "log", "text": f"\n[episode_query] DB FAILED: {e}\n"})
            state["task"]["need_episodes"] = False
            return state

        meta_line = (
            f"rows={meta.rows_returned} chars={meta.chars_returned} "
            f"truncated={meta.truncated} reason={meta.truncate_reason!r} elapsed_ms={meta.elapsed_ms}"
        )
        last_meta_text = meta_line
        emit({"type": "log", "text": f"\n[episode_query] meta: {meta_line}\n"})

        # --- LLM #2: summarize or request refine ---
        prompt_sum = deps.prompt_loader.render(
            "episode_sql_summarize",
            user_input=user_input,
            now=now,
            tz=tz,
            chat_history=chat_history,
            memories_summary=memories_summary,
            world_summary=world_summary,
            status=base_status if base_status else "(empty)",
            executed_sql=sql_text,
            rows=rows,
            truncated=str(bool(meta.truncated)).lower(),
            truncate_reason=meta.truncate_reason or "",
            rows_returned=str(meta.rows_returned),
            chars_returned=str(meta.chars_returned),
            elapsed_ms=str(meta.elapsed_ms),
        )

        decision = _collect_llm_response(deps, model=sum_model, prompt=prompt_sum, emit=emit).strip()

        emit({"type": "log", "text": f"\n[episode_query] decision:\n{decision}\n"})

        # Parse decision
        if decision.upper().startswith("FINAL:"):
            summary = decision[len("FINAL:") :].strip()
            state["context"]["episodes_summary"] = summary
            state["context"]["episodes_hits"] = rows

            # Stop further episodic requests this turn
            state["task"]["need_episodes"] = False

            if meta.truncated:
                _append_status(
                    state,
                    f"Episodic results truncated ({meta.truncate_reason}); summary reflects partial view.",
                )
            return state

        if decision.upper().startswith("REFINE_SQL:"):
            refine = decision[len("REFINE_SQL:") :].strip()
            # Feed refine hint back into author loop (do NOT execute directly)
            last_meta_text = (
                f"{meta_line}\n"
                f"Summarizer requested refine_sql hint:\n{refine}"
            )
            continue

        # Malformed summarizer output
        _append_status(state, "Episodic summarizer output malformed (expected FINAL: or REFINE_SQL:).")
        last_meta_text = "Summarizer output malformed."
        continue

    # Max rounds exceeded
    _append_status(state, "Episodic retrieval unresolved: max refinement rounds exceeded.")
    state["task"]["need_episodes"] = False
    return state
