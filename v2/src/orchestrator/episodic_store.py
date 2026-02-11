from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

_WINDHOEK_TZ = timezone(timedelta(hours=2))


@dataclass
class EpisodeRecord:
    ts_utc: str
    ts_local: str
    turn_id: str
    turn_seq: int
    project: str

    intent: str
    world_view: str
    retrieval_k: int

    user_text: str
    assistant_text: str

    rules_json: str
    world_before_json: str
    world_after_json: str
    world_delta_json: str
    memories_saved_json: str


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            ts_utc TEXT NOT NULL,
            ts_local TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            turn_seq INTEGER NOT NULL,
            project TEXT,
            intent TEXT,
            world_view TEXT,
            retrieval_k INTEGER,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            rules_json TEXT,
            world_before_json TEXT,
            world_after_json TEXT,
            world_delta_json TEXT,
            memories_saved_json TEXT
        )
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_utc ON episodes(ts_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_ts ON episodes(project, ts_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_turn_id ON episodes(turn_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intent_ts ON episodes(intent, ts_utc)")
    conn.commit()


def _episodes_db_path(cfg) -> Path:
    # Place episodes.sqlite next to openmemory database.
    # cfg.openmemory_db_path is authoritative.
    db_path = Path(cfg.openmemory_db_path)
    return db_path.parent / "episodes.sqlite"


def log_episode(cfg, record: EpisodeRecord) -> None:
    db_path = _episodes_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn)

        conn.execute(
            """
            INSERT INTO episodes (
                ts_utc, ts_local,
                turn_id, turn_seq,
                project,
                intent, world_view, retrieval_k,
                user_text, assistant_text,
                rules_json,
                world_before_json, world_after_json,
                world_delta_json,
                memories_saved_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.ts_utc,
                record.ts_local,
                record.turn_id,
                record.turn_seq,
                record.project,
                record.intent,
                record.world_view,
                record.retrieval_k,
                record.user_text,
                record.assistant_text,
                record.rules_json,
                record.world_before_json,
                record.world_after_json,
                record.world_delta_json,
                record.memories_saved_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def now_pair() -> tuple[str, str]:
    utc_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    local_now = datetime.now(tz=_WINDHOEK_TZ).isoformat(timespec="seconds")
    return utc_now, local_now
