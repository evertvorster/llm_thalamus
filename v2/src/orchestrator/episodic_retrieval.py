from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|create|attach|pragma|vacuum|reindex|begin|commit|rollback"
    r")\b",
    flags=re.IGNORECASE,
)

_FROM_OR_JOIN = re.compile(r"\b(from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class ExecMeta:
    truncated: bool
    truncate_reason: str  # "", "row_cap", "char_cap", "field_trim"
    rows_returned: int
    chars_returned: int
    elapsed_ms: int


def _strip_sql_comments(s: str) -> str:
    # Remove /* */ comments
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    # Remove -- comments
    s = re.sub(r"--[^\n]*", "", s)
    return s


def validate_select_sql(sql: str) -> tuple[bool, str]:
    if not isinstance(sql, str):
        return False, "sql is not a string"

    s = _strip_sql_comments(sql).strip()
    if not s:
        return False, "empty sql"

    if len(s) > 8192:
        return False, "sql too long"

    # Single statement: if there's a semicolon, it must be only trailing whitespace after it.
    semi = s.find(";")
    if semi != -1:
        tail = s[semi + 1 :].strip()
        if tail:
            return False, "multiple statements are not allowed"
        s = s[:semi].strip()

    if not re.match(r"(?is)^select\b", s):
        return False, "must start with SELECT"

    if _FORBIDDEN.search(s):
        return False, "contains forbidden keyword"

    # Only allow FROM/JOIN episodes
    tables = []
    for _, t in _FROM_OR_JOIN.findall(s):
        tables.append(t.lower())

    if tables:
        bad = [t for t in tables if t != "episodes"]
        if bad:
            return False, f"only 'episodes' table is allowed (found: {bad})"
    else:
        # If no FROM/JOIN found, it's suspicious but could be a SELECT literal.
        # Disallow for MVP.
        return False, "query must reference episodes table"

    return True, ""


def derive_episodes_db_path(*, openmemory_db_path: str) -> Path:
    """
    Episodes DB lives next to OpenMemory DB by convention:
      <dir>/episodes.sqlite
    """
    p = Path(openmemory_db_path)
    return p.with_name("episodes.sqlite")


def execute_select(
    *,
    db_path: Path,
    sql: str,
    max_rows: int,
    max_chars: int,
    field_trim: int,
) -> tuple[list[dict[str, Any]], ExecMeta]:
    """
    Execute a validated SELECT safely with enforced limits.
    - wraps query to enforce LIMIT max_rows
    - trims long text fields
    - caps total serialized output size to max_chars
    """
    t0 = time.time()

    # Clamp inputs
    if max_rows < 1:
        max_rows = 1
    if max_rows > 200:
        max_rows = 200
    if max_chars < 1000:
        max_chars = 1000
    if max_chars > 200_000:
        max_chars = 200_000
    if field_trim < 50:
        field_trim = 50
    if field_trim > 5000:
        field_trim = 5000

    # ---- FIX: normalize SQL for subquery wrapping ----
    # The SQL author often includes a trailing semicolon, which is legal for
    # sqlite3.execute(), but NOT legal inside a parenthesized subquery.
    sql_norm = (sql or "").strip()
    if sql_norm.endswith(";"):
        sql_norm = sql_norm[:-1].rstrip()
    # --------------------------------------------------

    rows_out: list[dict[str, Any]] = []
    truncated = False
    truncate_reason = ""
    chars_used = 0

    # Force a LIMIT regardless of author SQL.
    wrapped = f"SELECT * FROM ({sql_norm}) LIMIT ?"

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(wrapped, (max_rows,))
        cols = [d[0] for d in cur.description] if cur.description else []

        for r in cur.fetchall():
            d: dict[str, Any] = {}
            for c in cols:
                v = r[c]
                # Normalize bytes to str if any
                if isinstance(v, (bytes, bytearray)):
                    try:
                        v = v.decode("utf-8", errors="replace")
                    except Exception:
                        v = str(v)

                # Trim very long fields (especially user_text/assistant_text/json blobs)
                if isinstance(v, str) and len(v) > field_trim:
                    v = v[:field_trim] + "…"
                    truncated = True
                    truncate_reason = truncate_reason or "field_trim"

                d[c] = v

            # Budget: rough char cost
            item_cost = sum(len(str(k)) + len(str(v)) for k, v in d.items()) + 20
            if rows_out and (chars_used + item_cost) > max_chars:
                truncated = True
                truncate_reason = truncate_reason or "char_cap"
                break

            rows_out.append(d)
            chars_used += item_cost

        # If sqlite returned exactly max_rows, we might have truncated by row cap.
        # We cannot know if more existed without another query, so mark as row_cap
        # only if we didn't already hit char_cap.
        if len(rows_out) >= max_rows and not truncate_reason:
            truncated = True
            truncate_reason = "row_cap"

    finally:
        con.close()

    elapsed_ms = int((time.time() - t0) * 1000)
    meta = ExecMeta(
        truncated=truncated,
        truncate_reason=truncate_reason,
        rows_returned=len(rows_out),
        chars_returned=chars_used,
        elapsed_ms=elapsed_ms,
    )
    return rows_out, meta
