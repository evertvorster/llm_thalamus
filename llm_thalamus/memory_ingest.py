"""
memory_ingest.py

Ingestion helpers for llm-thalamus.

Two modes:

1. HTTP backend ingestion (advanced):
   - Requires an OpenMemory backend running and a backend_url in config.json:
        "openmemory": {
          "mode": "local",
          "path": "./data/memory.sqlite",
          "tier": "smart",
          "backend_url": "http://localhost:8080"
        }
   - Uses POST /memory/ingest with base64'd file bytes.
   - Lets the backend do full document/audio/video ingestion.

2. Standalone Python ingestion (fallback, current default):
   - If no backend_url is configured, we stay entirely in-process.
   - Reads the file as UTF-8 text and stores it via OpenMemory.add(...).
   - This is ideal for .md / .txt / code / JSON etc.

Hardening:
- In BOTH modes, every ingested file:
  - gets a "file_ingest" tag (in addition to any caller-provided tags)
  - gets metadata:
        kind="file_ingest"
        filename=<basename>
        path=<absolute-path>
        ingested_at=<ISO 8601 timestamp at ingest time>
  - caller metadata keys are merged without clobbering these base keys.
"""

from __future__ import annotations

import base64
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from llm_thalamus_internal.config import ThalamusConfig

import requests

from memory_retrieval import (  # reuse same config/user handling
    get_default_user_id,
    get_memory,
    run_om_async,
)

# ---------------------------------------------------------------------------
# Core ingestion helper
# ---------------------------------------------------------------------------

def ingest_file(
    file_path: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    content_type: Optional[str] = None,
    encoding_fallback: str = "application/octet-stream",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Ingest a single file into OpenMemory.

    Behaviour:
    - If config.openmemory.backend_url is set: HTTP ingestion.
    - Otherwise: standalone in-process ingestion into local store.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if user_id is None:
        user_id = get_default_user_id()

    # Prepare hardened tags used in BOTH modes
    base_tags: List[str] = ["file_ingest"]
    if tags:
        for t in tags:
            if t not in base_tags:
                base_tags.append(t)

    # Timestamp for this ingest (used for temporal version selection later)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Base metadata that cannot be overridden by caller metadata
    base_metadata: Dict[str, Any] = {
        "kind": "file_ingest",
        "filename": path.name,
        "path": str(path),
        "ingested_at": now_iso,
    }
    if metadata:
        # Don't clobber our base keys; caller wins on *other* keys.
        for k, v in metadata.items():
            if k not in base_metadata:
                base_metadata[k] = v

    cfg = ThalamusConfig.load()
    backend_url = cfg.openmemory.backend_url

    # ------------------------------------------------------------------
    # Mode 1: HTTP ingestion (backend_url configured)
    # ------------------------------------------------------------------
    if backend_url:
        ingest_url = f"{backend_url}/memory/ingest"

        # Guess content type if not provided
        if content_type is None:
            guessed, _ = mimetypes.guess_type(str(path))
            content_type = guessed or encoding_fallback

        # Read bytes and base64-encode
        data_bytes = path.read_bytes()
        data_b64 = base64.b64encode(data_bytes).decode("ascii")

        payload: Dict[str, Any] = {
            "content_type": content_type,
            "data": data_b64,
            "user_id": user_id,
            "metadata": base_metadata,
            "tags": base_tags,
        }

        response = requests.post(ingest_url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Mode 2: Standalone Python ingestion (no backend_url)
    # ------------------------------------------------------------------
    mem = get_memory()

    # Read as UTF-8 with replacement for any odd bytes
    text = path.read_text(encoding="utf-8", errors="replace")

    created = run_om_async(
        mem.add(
            text,
            user_id=user_id,
            metadata=base_metadata,
            tags=base_tags,
        )
    )

    return {
        "mode": "standalone",
        "file": str(path),
        "user_id": user_id,
        "metadata": base_metadata,
        "tags": base_tags,
        "memory": created,
    }
