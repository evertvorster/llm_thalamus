from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Tuple

from orchestrator.deps import Deps
from orchestrator.episodic_retrieval import (
    derive_episodes_db_path,
    execute_select,
    validate_select_sql,
)
from orchestrator.events import Event
from orchestrator.prompt_blocks import (
    render_chat_history,
    render_memories_summary,
    render_world_summary,
)
from orchestrator.state import State


# Internal loop controls (MVP defaults; can be moved to config later)
_MAX_EPISODE_ROUNDS = 8
_MAX_SQL_REJECTIONS = 3

_MAX_ROWS = 10_000
_MAX_CHARS = 32_000

# LLM-to-LLM mailbox budget (keep context pressure bounded)
_HANDOFF_MAX_CHARS = 4000
_HANDOFF_CONTEXT_KEY = "episodic_handoff"


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


def _append_episodic_debug(state: State, msg: str) -> None:
    """
    Debug channel for episodic internals. Unlike runtime.status, this should not
    cause the final node to short-circuit normal answering.
    """
    msg = (msg or "").strip()
    if not msg:
        return
    cur = (state.get("runtime", {}).get("episodic_debug") or "").strip()
    if not cur:
        state["runtime"]["episodic_debug"] = msg
    else:
        state["runtime"]["episodic_debug"] = cur + "\n" + msg


def _get_handoff(state: State) -> str:
    return str(state.get("context", {}).get(_HANDOFF_CONTEXT_KEY, "") or "").strip()


def _set_handoff(state: State, msg: str) -> None:
    msg = (msg or "").strip()
    if not msg:
        # Allow clearing
        state["context"][_HANDOFF_CONTEXT_KEY] = ""
        return

    # Keep only the tail to avoid ballooning context
    if len(msg) > _HANDOFF_MAX_CHARS:
        msg = msg[-_HANDOFF_MAX_CHARS:]

    state["context"][_HANDOFF_CONTEXT_KEY] = msg


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


_SQL_FENCED_BLOCK_RE = re.compile(r"(?is)```(?:sql|sqlite)\s*(.*?)\s*```")


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if "```" not in s:
        return s
    # Remove opening fence lines like ```sql\n or ```\n, keep content.
    s = re.sub(r"(?s)```[a-zA-Z0-9_-]*\n", "", s)
    # Remove remaining fences.
    s = s.replace("```", "")
    return s.strip()


def _extract_sql_statement(sql_text: str) -> str:
    """
    Extract one SQL statement from an LLM response.

    Preference order:
      1) First fenced ```sql (or ```sqlite) code block, verbatim.
      2) Otherwise, strip fences and take from the first SELECT/WITH token.

    If multiple statements are present, we keep only the first up to the first ';'.
    The validator enforces that any semicolon is trailing-only.
    """
    if not isinstance(sql_text, str):
        return ""

    raw = (sql_text or "").strip()

    m = _SQL_FENCED_BLOCK_RE.search(raw)
    if m:
        s = (m.group(1) or "").strip()
    else:
        s = _strip_code_fences(raw)

    # Find the first plausible start of a read-only query.
    m2 = re.search(r"(?is)\b(with|select)\b", s)
    if m2:
        s = s[m2.start() :].strip()

    semi = s.find(";")
    if semi != -1:
        s = s[: semi + 1].strip()

    return s.strip()


def _normalize_decision_prefix(decision: str) -> str:
    """
    Normalize the summarizer's decision channel so we can reliably parse:
      FINAL: ...
      TO_QUERY: ...
      REFINE_SQL: ...

    Models sometimes emit markdown like **FINAL:** or bullets/quotes. We strip
    lightweight wrappers only; we don't attempt to interpret content.
    """
    s = (decision or "").strip()
    if not s:
        return s

    # Remove leading quote / bullet / emphasis noise (common in LLM outputs)
    s = s.lstrip(" \t\r\n>*_-")

    # Handle common bold markers: **FINAL:**, **TO_QUERY:**, **REFINE_SQL:**
    # Do a conservative replacement at the beginning only.
    s = re.sub(r"(?i)^\*{1,3}\s*(FINAL|TO_QUERY|REFINE_SQL)\s*:\s*\*{1,3}\s*", r"\1: ", s)

    # Also handle the case where only the left-side is bolded: **FINAL:** blah
    s = re.sub(r"(?i)^\*{2}\s*(FINAL|TO_QUERY|REFINE_SQL)\s*:\s*", r"\1: ", s)

    return s.strip()


def run_episode_query_node(
    state: State,
    deps: Deps,
    *,
    emit: Callable[[Event], None],
) -> State:
    """
    Episodic retrieval node:

      - LLM #1 authors SQL (read-only)
      - validate SQL mechanically (hard gate)
      - execute with strict budgets (rows/chars/field trim)
      - LLM #2 either:
          FINAL: <summary>
          TO_QUERY: <handoff message to SQL LLM>
        (REFINE_SQL: is accepted as an alias for TO_QUERY:)

      - loops internally up to _MAX_EPISODE_ROUNDS
      - writes results into state.context.episodes_summary / episodes_hits
      - uses state.runtime.status only for terminal failure diagnostics
      - uses state.runtime.episodic_debug for verbose internal debug trail

    Key design: the SQL LLM and summarizer communicate via state.context.episodic_handoff.
    """
    # If already have a summary, treat as done.
    if (state.get("context", {}).get("episodes_summary") or "").strip():
        state["task"]["need_episodes"] = False
        return state

    sql_model, sum_model = _choose_models(deps)

    # Ensure context dict exists
    state.setdefault("context", {})

    # Derive DB path (episodes.sqlite next to OpenMemory DB)
    db_path: Path = derive_episodes_db_path(openmemory_db_path=str(deps.cfg.openmemory_db_path))

    # Build the "router-equivalent" context blocks (parity guarantee)
    w = state.get("world") or {}
    now = str(w.get("now", "") or "")
    tz = str(w.get("tz", "") or "")

    user_input = state["task"]["user_input"]
    chat_history = render_chat_history(state)
    memories_summary = render_memories_summary(state)
    world_summary = render_world_summary(state)

    base_status = (state.get("runtime", {}).get("status") or "").strip()

    # Loop control
    last_sql = ""
    last_meta_text = ""
    sql_rejections = 0

    for round_idx in range(1, _MAX_EPISODE_ROUNDS + 1):
        emit({"type": "log", "text": f"\n[episode_query] round {round_idx}/{_MAX_EPISODE_ROUNDS}\n"})

        handoff = _get_handoff(state)
        if handoff:
            emit({"type": "log", "text": f"\n[episode_query] handoff_to_sql:\n{handoff}\n"})

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
            handoff=handoff if handoff else "(none)",
        )

        sql_text_raw = _collect_llm_response(deps, model=sql_model, prompt=prompt_sql, emit=emit)

        # IMPORTANT: extract a single SQL statement (prefer fenced ```sql blocks).
        sql_text = _extract_sql_statement(sql_text_raw)

        last_sql = sql_text
        emit({"type": "log", "text": f"\n[episode_query] sql_candidate:\n{sql_text}\n"})

        ok, reason = validate_select_sql(sql_text)
        if not ok:
            sql_rejections += 1
            emit({"type": "log", "text": f"\n[episode_query] SQL rejected: {reason}\n"})
            _append_episodic_debug(state, f"Episodic SQL rejected: {reason}")
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

        if meta.truncated:
            _append_episodic_debug(
                state,
                f"Episodic results truncated ({meta.truncate_reason}); summary should acknowledge partial view.",
            )

        # --- LLM #2: summarize or request next step to SQL LLM ---
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
            handoff=handoff if handoff else "(none)",
        )

        decision_raw = _collect_llm_response(deps, model=sum_model, prompt=prompt_sum, emit=emit).strip()
        emit({"type": "log", "text": f"\n[episode_query] decision:\n{decision_raw}\n"})

        decision = _normalize_decision_prefix(decision_raw)

        # Parse decision
        if decision.upper().startswith("FINAL:"):
            summary = decision[len("FINAL:") :].strip()
            state["context"]["episodes_summary"] = summary
            state["context"]["episodes_hits"] = rows

            # Stop further episodic requests this turn
            state["task"]["need_episodes"] = False
            return state

        # Back-compat: treat REFINE_SQL as a handoff to the SQL LLM
        if decision.upper().startswith("REFINE_SQL:"):
            msg = decision[len("REFINE_SQL:") :].strip()
            _set_handoff(state, msg)
            last_meta_text = f"{meta_line}\nSummarizer->SQL handoff (REFINE_SQL):\n{msg}"
            continue

        if decision.upper().startswith("TO_QUERY:"):
            msg = decision[len("TO_QUERY:") :].strip()
            _set_handoff(state, msg)
            last_meta_text = f"{meta_line}\nSummarizer->SQL handoff:\n{msg}"
            continue

        # Malformed summarizer output — treat as debug, allow refinement loop to continue.
        _append_episodic_debug(
            state,
            "Episodic summarizer output malformed (expected FINAL: or TO_QUERY:). "
            "Raw decision:\n" + decision_raw
        )
        last_meta_text = "Summarizer output malformed."
        continue

    # Max rounds exceeded (terminal)
    _append_status(state, "Episodic retrieval unresolved: max refinement rounds exceeded.")
    state["task"]["need_episodes"] = False
    return state
