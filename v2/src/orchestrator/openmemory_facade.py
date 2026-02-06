from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from thalamus_openmemory.api.reader import search_memories
from thalamus_openmemory.api.writer import add_memory


# NOTE:
# We intentionally normalize timestamps here (OpenMemory boundary) so downstream nodes
# can remain schema-agnostic. OpenMemory records include an epoch-ms creation time at:
#   record["metadata"]["ingested_at"]
# We expose this as ISO8601 on:
#   record["ts"]  (and also metadata["ts"] for convenience/back-compat).


_WINDHOEK_TZ = timezone(timedelta(hours=2))  # Africa/Windhoek (CAT, UTC+02:00)


def _ms_to_iso8601(ms: int) -> str:
    # Keep millisecond precision (OpenMemory stores epoch ms).
    dt = datetime.fromtimestamp(ms / 1000.0, tz=_WINDHOEK_TZ)
    return dt.isoformat(timespec="milliseconds")


def _coerce_epoch_ms(v: object) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        # Allow floats that represent ms.
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


def _attach_ts(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a shallow-copied record with ISO8601 creation timestamp attached when available.

    - Source field: record["metadata"]["ingested_at"] (epoch ms)
    - Added fields:
        record["ts"] = "<iso8601>"
        record["metadata"]["ts"] = "<iso8601>"
    """
    if not isinstance(record, dict):
        return record

    meta = record.get("metadata")
    if not isinstance(meta, dict):
        return record

    ingested_at_ms = _coerce_epoch_ms(meta.get("ingested_at"))
    if ingested_at_ms is None:
        return record

    ts = _ms_to_iso8601(ingested_at_ms)

    # Shallow copy to avoid mutating caller-visible dicts from the API layer.
    out = dict(record)
    out["ts"] = ts

    meta_out = dict(meta)
    meta_out["ts"] = ts
    out["metadata"] = meta_out

    return out


@dataclass(frozen=True)
class OpenMemoryFacade:
    """
    Thin boundary around OpenMemory that:
      - exposes a minimal API to the orchestrator
      - does NOT accept or pass user_id

    Assumption (your stated design):
      - OpenMemory is configured at startup (bootstrap) and applies user scoping internally.
      - Therefore callers must never pass user_id.
    """
    _client: Any

    def search(self, query: str, *, k: int) -> List[Dict[str, Any]]:
        # Intentionally do NOT pass user_id.
        raw = search_memories(
            self._client,
            query=query,
            k=k,
        )

        if not raw:
            return []

        out: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(_attach_ts(item))
            else:
                # Preserve non-dict items as-is (defensive).
                out.append(item)
        return out

    def add(self, text: str) -> Dict[str, Any]:
        # Intentionally do NOT pass user_id.
        rec = add_memory(
            self._client,
            text,
        )
        if isinstance(rec, dict):
            return _attach_ts(rec)
        return rec
