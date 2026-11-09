"""What pi-memory spent tagging this session.

The tagger is a separate process calling the provider with its own key, so pi
counts none of it: the cost of adding memory to a session is invisible in every
number the panel already shows.  pi-memory records it per turn, and this reads
that record — read-only, tolerant of the database being absent or busy.

Tagging runs on demand, so the figure lags the conversation; a session that has
not been tagged yet reports nothing rather than zero.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

__all__ = ["database", "session_tag_spend", "session_uuid"]


def database() -> Path:
    """The pi-memory database, wherever that install keeps it."""
    root = os.environ.get("PI_MEMORY_DIR")
    if root:
        return Path(root) / "memory.db"
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "pi-memory" / "memory.db"


def session_uuid(session_file: str | None) -> str | None:
    """The pi session id from a session file name (``<timestamp>_<uuid>.jsonl``)."""
    if not session_file:
        return None
    _, _, uid = Path(session_file).stem.partition("_")
    return uid or None


def session_tag_spend(session_id: str | None,
                      db_path: Path | None = None) -> tuple[int, float] | None:
    """(calls, dollars) spent tagging this session, or None if nothing is known."""
    if not session_id:
        return None
    path = db_path or database()
    if not path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            row = con.execute(
                "select count(*), coalesce(sum(tag_cost), 0) from turns "
                "where session_id = ? and tag_in_tok is not null",
                (session_id,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return int(row[0]), float(row[1])
