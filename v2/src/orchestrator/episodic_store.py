from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

_WINDHOEK_TZ = timezone(timedelta(hours=2))


@dataclass
class EpisodeRecord:
    # timeline / ids
    ts_utc: str
    ts_local: str
    turn_id: str
    turn_seq: int

    # router metadata
    intent: str
    world_view: str
    retrieval_k: int

    # world_state flattened (WORLD AFTER is definitive)
    updated_at: str
    project: str
    topics_json: str
    goals_json: str
    rules_json: str

    identity_user_name: str
    identity_session_user_name: str
    identity_agent_name: str
    identity_user_location: str

    # payload
    user_text: str
    assistant_text: str

    # audit/debug payload
    world_before_json: str
    world_after_json: str
    world_delta_json: str
    memories_saved_json: str


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,

            -- timeline / ids
            ts_utc TEXT NOT NULL,
            ts_local TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            turn_seq INTEGER NOT NULL,

            -- router metadata
            intent TEXT,
            world_view TEXT,
            retrieval_k INTEGER,

            -- world_state flattened (WORLD AFTER is definitive)
            updated_at TEXT,
            project TEXT,
            topics_json TEXT,
            goals_json TEXT,
            rules_json TEXT,

            identity_user_name TEXT,
            identity_session_user_name TEXT,
            identity_agent_name TEXT,
            identity_user_location TEXT,

            -- payload
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,

            -- audit/debug payload
            world_before_json TEXT,
            world_after_json TEXT,
            world_delta_json TEXT,
            memories_saved_json TEXT
        )
        """
    )

    # indexes (keep them practical and stable)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_utc ON episodes(ts_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_local ON episodes(ts_local)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_ts ON episodes(project, ts_local)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_turn_id ON episodes(turn_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_intent_ts ON episodes(intent, ts_local)")
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
                ts_utc, ts_local, turn_id, turn_seq,
                intent, world_view, retrieval_k,

                updated_at, project, topics_json, goals_json, rules_json,
                identity_user_name, identity_session_user_name, identity_agent_name, identity_user_location,

                user_text, assistant_text,

                world_before_json, world_after_json, world_delta_json, memories_saved_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.ts_utc,
                record.ts_local,
                record.turn_id,
                record.turn_seq,
                record.intent,
                record.world_view,
                record.retrieval_k,
                record.updated_at,
                record.project,
                record.topics_json,
                record.goals_json,
                record.rules_json,
                record.identity_user_name,
                record.identity_session_user_name,
                record.identity_agent_name,
                record.identity_user_location,
                record.user_text,
                record.assistant_text,
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
