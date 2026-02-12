from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    """
    Lightweight, policy-oriented validation.

    We intentionally do NOT try to fully "parse" SQL with regex. SQLite itself
    will validate syntax. Our goal is to:
      - ensure a single statement
      - ensure it's a read-only query shape (SELECT/CTE)
      - keep input size bounded (anti-garbage)
    """
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

    # Allow SELECT or CTE-leading WITH.
    if not re.match(r"(?is)^(select|with)\b", s):
        return False, "must start with SELECT or WITH"

    return True, ""


def derive_episodes_db_path(*, openmemory_db_path: str) -> Path:
    """
    Episodes DB lives next to OpenMemory DB by convention:
      <dir>/episodes.sqlite
    """
    p = Path(openmemory_db_path)
    return p.with_name("episodes.sqlite")


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Open the episodes DB in enforced read-only mode.

    - file:...?... mode=ro prevents write transactions at the filesystem level
    - PRAGMA query_only=ON prevents write opcodes even if permissions were loose
    """
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.execute("PRAGMA query_only = ON;")
    return con


def execute_select(
    *,
    db_path: Path,
    sql: str,
    max_rows: int,
    max_chars: int,
    field_trim: int,
) -> tuple[list[dict[str, Any]], ExecMeta]:
    """
    Execute a validated read-only SQL query with enforced output budgets.

    We do NOT rewrite the SQL (no wrapper LIMIT), because that can break valid
    queries (e.g. CTEs starting with WITH). Instead, we:
      - open the DB read-only
      - execute the query as-is
      - cap returned rows and serialized output size
      - trim very long text fields
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

    sql_norm = (sql or "").strip()
    if sql_norm.endswith(";"):
        sql_norm = sql_norm[:-1].rstrip()

    rows_out: list[dict[str, Any]] = []
    truncated = False
    truncate_reason = ""
    chars_used = 0

    con = _connect_readonly(db_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql_norm)
        cols = [d[0] for d in cur.description] if cur.description else []

        # Fetch rows iteratively so we can enforce row/char caps without rewriting SQL.
        while True:
            if len(rows_out) >= max_rows:
                break

            chunk = cur.fetchmany(min(50, max_rows - len(rows_out)))
            if not chunk:
                break

            for r in chunk:
                d: dict[str, Any] = {}
                for c in cols:
                    v = r[c]
                    if isinstance(v, (bytes, bytearray)):
                        try:
                            v = v.decode("utf-8", errors="replace")
                        except Exception:
                            v = str(v)

                    if isinstance(v, str) and len(v) > field_trim:
                        v = v[:field_trim] + "…"
                        truncated = True
                        truncate_reason = truncate_reason or "field_trim"

                    d[c] = v

                item_cost = sum(len(str(k)) + len(str(v)) for k, v in d.items()) + 20
                if rows_out and (chars_used + item_cost) > max_chars:
                    truncated = True
                    truncate_reason = truncate_reason or "char_cap"
                    break

                rows_out.append(d)
                chars_used += item_cost

                if len(rows_out) >= max_rows:
                    break

            if truncate_reason == "char_cap":
                break

        # Determine row_cap truncation only if we didn't already hit char_cap.
        if len(rows_out) >= max_rows and truncate_reason != "char_cap":
            # Peek one more row to see whether there was more data.
            try:
                extra = cur.fetchone()
            except Exception:
                extra = None
            if extra is not None:
                truncated = True
                truncate_reason = truncate_reason or "row_cap"

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
