#!/usr/bin/env python3
"""
spaces_manager – SQLite-backed Spaces & Objects manager for llm-thalamus.

Responsibilities:
- Own the SQLite DB that lives alongside OpenMemory's memory.sqlite.
- Manage:
    - Spaces (id, name, description, active)
    - Objects (id, space_id, name=filename, object_type, active)
    - Versions (id, object_id, filename, original_path, ingested_at,
                openmemory_id, status)

- Provide a clean Python API for:
    - UI (create/list/toggle spaces, objects, versions)
    - Thalamus (get_active_documents_for_prompt)

- Integrate with:
    - memory_ingest.ingest_file(...) for file ingestion
    - memory_document_retrieval.retrieve_document_from_metadata(...)
      for document retrieval using filename + tags.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from paths import get_user_config_path

from memory_ingest import ingest_file
from memory_retrieve_documents import (
    retrieve_document_from_metadata,
    retrieve_document_by_id,
)


logger = logging.getLogger("spaces_manager")

# ---------------------------------------------------------------------------
# Config & DB path handling
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = get_user_config_path()

_DB_CONN: Optional[sqlite3.Connection] = None


def _load_config() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config.json at: {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_db_path() -> Path:
    """
    Derive spaces.db path from the OpenMemory path in config.

    If openmemory.path is ./data/memory.sqlite, we use ./data/spaces.db.
    """
    cfg = _load_config()
    om_cfg = cfg.get("openmemory", {})
    om_path = Path(om_cfg["path"]).expanduser().resolve()
    return om_path.parent / "spaces.db"


def _init_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they don't exist.
    """
    cur = conn.cursor()

    # Spaces table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS spaces (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL
        );
        """
    )

    # Objects table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS objects (
            id          INTEGER PRIMARY KEY,
            space_id    INTEGER NOT NULL REFERENCES spaces(id) ON DELETE RESTRICT,
            name        TEXT NOT NULL,
            object_type TEXT NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_objects_space_name
            ON objects(space_id, name);
        """
    )

    # Versions table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS versions (
            id            INTEGER PRIMARY KEY,
            object_id     INTEGER NOT NULL REFERENCES objects(id) ON DELETE RESTRICT,
            filename      TEXT NOT NULL,
            original_path TEXT NOT NULL,
            ingested_at   TEXT NOT NULL,
            openmemory_id TEXT NOT NULL,
            status        TEXT NOT NULL CHECK(status IN ('active','inactive','error')),
            note          TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_versions_object
            ON versions(object_id);
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_versions_status
            ON versions(status);
        """
    )

    # Settings table for global key/value pairs (e.g. current_space_id)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )

    conn.commit()


def get_db() -> sqlite3.Connection:
    """
    Return a singleton SQLite connection to spaces.db.

    Uses WAL and foreign_keys=ON.
    """
    global _DB_CONN
    if _DB_CONN is None:
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _init_schema(conn)
        _DB_CONN = conn
        logger.info("Spaces DB initialized at %s", db_path)
    return _DB_CONN


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data representations
# ---------------------------------------------------------------------------

@dataclass
class Space:
    id: int
    name: str
    description: str
    active: bool
    created_at: str


@dataclass
class Object:
    id: int
    space_id: int
    name: str
    object_type: str
    active: bool
    created_at: str


@dataclass
class Version:
    id: int
    object_id: int
    filename: str
    original_path: str
    ingested_at: str
    openmemory_id: str
    status: str
    note: str


# ---------------------------------------------------------------------------
# SpacesManager
# ---------------------------------------------------------------------------

class SpacesManager:
    """
    Main entry point for managing spaces, objects, and versions.

    All methods are synchronous and assume single-process access, but
    SQLite WAL mode is enabled for modest concurrency.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None) -> None:
        self.conn = conn or get_db()

    # -------------------- Spaces --------------------

    def create_space(self, name: str, description: str = "") -> int:
        """
        Create a new Space (active by default) and return its id.
        """
        name = name.strip()
        if not name:
            raise ValueError("Space name cannot be empty")

        created_at = _utc_now_iso()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO spaces (name, description, active, created_at)
            VALUES (?, ?, 1, ?)
            """,
            (name, description, created_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_spaces(self, active_only: bool = False) -> List[Space]:
        """
        List spaces, optionally only active ones.

        Results are sorted: active spaces first, then inactive, by id.
        """
        cur = self.conn.cursor()
        if active_only:
            cur.execute(
                """
                SELECT id, name, description, active, created_at
                FROM spaces
                WHERE active = 1
                ORDER BY id ASC
                """
            )
        else:
            cur.execute(
                """
                SELECT id, name, description, active, created_at
                FROM spaces
                ORDER BY active DESC, id ASC
                """
            )
        rows = cur.fetchall()
        return [
            Space(
                id=row["id"],
                name=row["name"],
                description=row["description"] or "",
                active=bool(row["active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def set_space_active(self, space_id: int, active: bool) -> None:
        """
        Toggle the 'active' flag for a single space.

        - Multiple spaces may be active at once. This flag is used purely for
        UI sorting/enabling (e.g. greying out inactive spaces).
        - The *current* entered space whose documents are exposed to Thalamus
        is tracked separately via settings.current_space_id.
        """
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE spaces SET active = ? WHERE id = ?",
            (1 if active else 0, space_id),
        )
        self.conn.commit()

    def delete_space(self, space_id: int) -> None:
        """
        Delete a space **only if it contains no objects**.

        This prevents accidental mass deletion. Users must explicitly delete
        all objects (and their versions) before removing the space itself.

        Raises:
            ValueError: if the space still contains objects.
        """
        cur = self.conn.cursor()

        # Check if space exists
        cur.execute("SELECT id FROM spaces WHERE id = ?", (space_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Space id {space_id} does not exist.")

        # Check if the space contains objects
        cur.execute("SELECT COUNT(*) AS cnt FROM objects WHERE space_id = ?", (space_id,))
        row = cur.fetchone()
        if row and row["cnt"] > 0:
            raise ValueError(
                "Cannot delete this space because it still contains objects.\n"
                "Please delete all objects from the space first."
            )

        # Clear current_space_id if it matches
        cur.execute("SELECT value FROM settings WHERE key = 'current_space_id'")
        row = cur.fetchone()
        if row and str(row["value"]) == str(space_id):
            cur.execute("DELETE FROM settings WHERE key = 'current_space_id'")

        # Delete the space itself
        cur.execute("DELETE FROM spaces WHERE id = ?", (space_id,))
        self.conn.commit()


    # -------------------- Current space (for Thalamus) --------------------

    def set_current_space_id(self, space_id: Optional[int]) -> None:
        """
        Persist the current 'entered' space.

        - None means: no space is currently entered (root view).
        """
        cur = self.conn.cursor()
        if space_id is None:
            cur.execute("DELETE FROM settings WHERE key = 'current_space_id'")
        else:
            cur.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('current_space_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(space_id),),
            )
        self.conn.commit()

    def get_current_space_id(self) -> Optional[int]:
        """
        Return the id of the space currently 'entered' in the UI, or None.
        """
        cur = self.conn.cursor()
        cur.execute(
            "SELECT value FROM settings WHERE key = 'current_space_id'"
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    # -------------------- Objects --------------------

    def create_object_for_file(
        self,
        space_id: int,
        file_path: str,
        object_type: str = "text_file",
    ) -> int:
        """
        Create a new Object for a given file and ingest the file as the first Version.

        - Object name is the basename of the file and is immutable.
        - Ensures uniqueness of (space_id, name).
        - Returns the object_id.
        """
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {p}")

        filename = p.name
        created_at = _utc_now_iso()

        cur = self.conn.cursor()
        # Ensure space exists
        cur.execute("SELECT id, name FROM spaces WHERE id = ?", (space_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Space id {space_id} does not exist")
        space_name = row["name"]

        # Insert object; will raise IntegrityError if (space_id, name) already exists
        try:
            cur.execute(
                """
                INSERT INTO objects (space_id, name, object_type, active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (space_id, filename, object_type, created_at),
            )
            object_id = cur.lastrowid
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            # Likely uniqueness violation on (space_id, name)
            raise ValueError(
                f"An object named {filename!r} already exists in this space"
            ) from e

        # Create first version via ingestion
        self.add_version(object_id, str(p), space_name=space_name, object_name=filename)

        return object_id

    def list_objects(self, space_id: int, active_only: bool = False) -> List[Object]:
        """
        List objects in a space, optionally only active ones.
        """
        cur = self.conn.cursor()
        if active_only:
            cur.execute(
                """
                SELECT id, space_id, name, object_type, active, created_at
                FROM objects
                WHERE space_id = ? AND active = 1
                ORDER BY id ASC
                """,
                (space_id,),  # IMPORTANT: tuple, not plain space_id
            )
        else:
            cur.execute(
                """
                SELECT id, space_id, name, object_type, active, created_at
                FROM objects
                WHERE space_id = ?
                ORDER BY active DESC, id ASC
                """,
                (space_id,),  # IMPORTANT: tuple, not plain space_id
            )

        rows = cur.fetchall()
        return [
            Object(
                id=row["id"],
                space_id=row["space_id"],
                name=row["name"],
                object_type=row["object_type"],
                active=bool(row["active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def set_object_active(self, object_id: int, active: bool) -> None:
        """
        Toggle object active flag.
        """
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE objects SET active = ? WHERE id = ?",
            (1 if active else 0, object_id),
        )
        self.conn.commit()

    # -------------------- Versions --------------------

    def add_version(
        self,
        object_id: int,
        file_path: str,
        *,
        space_name: Optional[str] = None,
        object_name: Optional[str] = None,
    ) -> int:
        """
        Ingest a new version for an existing object.

        - Validates that the file's basename matches the object's name.
        - Calls memory_ingest.ingest_file(...) with appropriate tags/metadata.
        - Inserts a new row into versions with status='active'.
        - Returns version_id.
        """
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {p}")

        basename = p.name

        cur = self.conn.cursor()
        # Look up object and owning space
        cur.execute(
            """
            SELECT o.id, o.space_id, o.name AS object_name,
                   s.name AS space_name
            FROM objects o
            JOIN spaces s ON s.id = o.space_id
            WHERE o.id = ?
            """,
            (object_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Object id {object_id} does not exist")

        obj_name = row["object_name"]
        space_id = row["space_id"]
        sp_name = row["space_name"]

        # Enforce basename invariant
        if basename != obj_name:
            raise ValueError(
                f"File basename {basename!r} does not match object name {obj_name!r}. "
                "If you renamed the file, create a new object."
            )

        # Prepare tags and metadata for ingestion
        tags = [
            "llm-thalamus",
            f"space:{space_id}",
            f"object:{object_id}",
            "type:text_file",
        ]
        metadata = {
            "space_id": space_id,
            "space_name": space_name or sp_name,
            "object_id": object_id,
            "object_name": object_name or obj_name,
            "object_type": "text_file",
        }

        # Ingest file via memory_ingest
        try:
            result = ingest_file(str(p), metadata=metadata, tags=tags)
        except Exception as e:
            logger.warning("Ingestion failed for %s: %s", p, e, exc_info=True)
            # Insert an error version? For now, we do NOT create a version on failure.
            raise

        # Extract OpenMemory id and ingested_at
        # Standalone mode: result["memory"] is the created memory object and
        # result["metadata"]["ingested_at"] is the timestamp.
        memory = result.get("memory") or {}
        openmemory_id = str(memory.get("id") or memory.get("memoryId") or "")
        meta_after = result.get("metadata") or {}
        ingested_at = meta_after.get("ingested_at")

        if not openmemory_id:
            logger.warning(
                "Ingest result missing memory id for %s, result=%r", p, result
            )
            raise RuntimeError("Ingest result missing memory id")

        if not ingested_at:
            logger.warning(
                "Ingest result missing ingested_at for %s, result=%r", p, result
            )
            # Fall back to now
            ingested_at = _utc_now_iso()

        cur.execute(
            """
            INSERT INTO versions (
                object_id, filename, original_path,
                ingested_at, openmemory_id, status, note
            ) VALUES (?, ?, ?, ?, ?, 'active', NULL)
            """,
            (object_id, basename, str(p), ingested_at, openmemory_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_versions(self, object_id: int) -> List[Version]:
        """
        List versions for an object, newest first.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, object_id, filename, original_path,
                   ingested_at, openmemory_id, status, note
            FROM versions
            WHERE object_id = ?
            ORDER BY ingested_at DESC, id DESC
            """,
            (object_id,),
        )
        rows = cur.fetchall()
        return [
            Version(
                id=row["id"],
                object_id=row["object_id"],
                filename=row["filename"],
                original_path=row["original_path"],
                ingested_at=row["ingested_at"],
                openmemory_id=row["openmemory_id"],
                status=row["status"],
                note=row["note"] or "",
            )
            for row in rows
        ]

    def set_version_status(self, version_id: int, status: str) -> None:
        """
        Set the status of a version: 'active', 'inactive', or 'error'.
        """
        if status not in ("active", "inactive", "error"):
            raise ValueError(f"Invalid version status: {status!r}")

        cur = self.conn.cursor()
        cur.execute(
            "UPDATE versions SET status = ? WHERE id = ?",
            (status, version_id),
        )
        self.conn.commit()

    def delete_version(self, version_id: int) -> None:
        """
        Permanently delete a version and its OpenMemory entry.

        Behaviour:
        - Delete the associated OpenMemory memory (best effort).
        - Delete the version row from the local DB.
        - If that was the last version for its object, delete the object too.

        Other objects and versions are unaffected.
        """
        cur = self.conn.cursor()

        # Look up the version and its owning object
        cur.execute(
            """
            SELECT object_id, openmemory_id
            FROM versions
            WHERE id = ?
            """,
            (version_id,),
        )
        row = cur.fetchone()
        if not row:
            return  # nothing to do

        object_id = row["object_id"]
        openmemory_id = row["openmemory_id"]

        # 1) Try to delete from OpenMemory
        if openmemory_id:
            try:
                # Local import to avoid any risk of circular imports
                from memory_storage import delete_memory
                delete_memory(openmemory_id)
            except Exception as e:
                logger.warning(
                    "Failed to delete OpenMemory entry %s for version %s: %s",
                    openmemory_id,
                    version_id,
                    e,
                )

        # 2) Delete the version row itself
        cur.execute(
            "DELETE FROM versions WHERE id = ?",
            (version_id,),
        )

        # 3) If this was the last version, delete the object as well
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM versions WHERE object_id = ?",
            (object_id,),
        )
        count_row = cur.fetchone()
        remaining = count_row["cnt"] if count_row else 0

        if remaining == 0:
            cur.execute(
                "DELETE FROM objects WHERE id = ?",
                (object_id,),
            )

        self.conn.commit()


    # -------------------- Thalamus integration --------------------

    def get_active_documents_for_prompt(self) -> List[Dict[str, str]]:
        """
        Return a list of {name, text} docs to be injected as INTERNAL open
        documents for the LLM.

        Strategy:
        - Look at the *current* entered space (settings.current_space_id).
        - If no space is entered, return an empty list (no documents).
        - Within that space, consider active objects and versions with status='active'.
        - For each object, select the latest active version by ingested_at.
        - For each selected version, retrieve document text using
          retrieve_document_by_id(...), using the exact OpenMemory id
          we stored at ingest time.
        """
        current_space_id = self.get_current_space_id()
        if current_space_id is None:
            return []

        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                s.id AS space_id,
                o.id AS object_id,
                o.name AS object_name,
                v.id AS version_id,
                v.ingested_at,
                v.openmemory_id AS openmemory_id,
                v.filename AS filename
            FROM spaces s
            JOIN objects o ON o.space_id = s.id
            JOIN versions v ON v.object_id = o.id
            WHERE s.id = ?
              AND o.active = 1
              AND v.status = 'active'
            ORDER BY o.id ASC, v.ingested_at DESC, v.id DESC
            """,
            (current_space_id,),
        )
        rows = cur.fetchall()

        # Group by object_id and keep the first row per object (latest due to ORDER BY)
        latest_by_object: Dict[int, sqlite3.Row] = {}
        for row in rows:
            obj_id = row["object_id"]
            if obj_id not in latest_by_object:
                latest_by_object[obj_id] = row

        documents: List[Dict[str, str]] = []

        for row in latest_by_object.values():
            space_id = row["space_id"]
            object_id = row["object_id"]
            object_name = row["object_name"]
            openmemory_id = str(row["openmemory_id"] or "")
            filename = row["filename"] or object_name

            if not openmemory_id:
                logger.warning(
                    "Skipping object_id=%s (%r): missing openmemory_id",
                    object_id,
                    object_name,
                )
                continue

            try:
                # Pure ID-based retrieval: no tags, no guessing.
                text = retrieve_document_by_id(openmemory_id)
            except Exception as e:
                logger.warning(
                    "Failed to retrieve document by id for object_id=%s, filename=%r, "
                    "openmemory_id=%s: %s",
                    object_id,
                    filename,
                    openmemory_id,
                    e,
                    exc_info=True,
                )
                continue

            if not text:
                logger.warning(
                    "Empty text returned for object_id=%s, filename=%r, "
                    "openmemory_id=%s",
                    object_id,
                    filename,
                    openmemory_id,
                )
                continue

            documents.append(
                {
                    "name": object_name,
                    "text": text,
                }
            )

        return documents


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_MANAGER: Optional[SpacesManager] = None


def get_manager() -> SpacesManager:
    """
    Return a singleton SpacesManager instance.
    """
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SpacesManager(get_db())
    return _MANAGER
