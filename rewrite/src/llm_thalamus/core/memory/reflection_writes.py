from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import logging
import re

from llm_thalamus.adapters.openmemory.client import assert_db_present
from llm_thalamus.core.memory.store_memories import delete_memory, store_memory


@dataclass(frozen=True)
class MemoryWrite:
    content: str
    tags: List[str]
    metadata: Dict[str, Any]


_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", flags=re.DOTALL | re.IGNORECASE)


def _extract_last_json_fence(text: str) -> Optional[str]:
    blocks = _JSON_FENCE_RE.findall(text)
    return blocks[-1] if blocks else None


def _coerce_tags(item: Dict[str, Any]) -> List[str]:
    tag = item.get("tag")
    if isinstance(tag, str) and tag.strip():
        return [tag.strip()]

    tags = item.get("tags")
    if isinstance(tags, list):
        out: List[str] = []
        for t in tags:
            if isinstance(t, str) and t.strip() and t.strip() not in out:
                out.append(t.strip())
        return out

    return []


def parse_memory_writes(reflection_text: str) -> List[MemoryWrite]:
    text = (reflection_text or "").strip()
    if not text:
        return []

    fenced = _extract_last_json_fence(text)
    if fenced:
        payload = json.loads(fenced)
    else:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payload = json.loads(stripped)
        else:
            return []

    if not isinstance(payload, dict):
        return []

    writes = payload.get("memory_writes")
    if not isinstance(writes, list):
        return []

    out: List[MemoryWrite] = []
    for item in writes:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue

        tags = _coerce_tags(item)

        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        out.append(MemoryWrite(content=content, tags=tags, metadata=metadata))
    return out


def fallback_chunk_reflection(reflection_text: str) -> List[str]:
    text = (reflection_text or "").strip()
    if not text:
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = [
        chunk.strip()
        for chunk in re.split(r"\n\s*\n+", normalized)
        if chunk.strip()
    ]
    return chunks


def store_reflection_writes(
    reflection_text: str,
    *,
    session_id: str,
    timestamp: Optional[str] = None,
    allow_fallback_chunking: bool = True,
) -> List[str]:
    """
    Store reflection output as memory writes and return created memory ids.

    Requires real OpenMemory DB to exist (probe-friendly).
    """
    assert_db_present()

    log = logging.getLogger("thalamus")
    text = (reflection_text or "").strip()
    if not text:
        return []

    _ = session_id  # reserved for future metadata policy
    _ = timestamp or datetime.utcnow().isoformat(timespec="seconds") + "Z"

    created_ids: List[str] = []

    try:
        writes = parse_memory_writes(text)
        if writes:
            for w in writes:
                res = store_memory(content=w.content, tags=w.tags, metadata=w.metadata)
                if isinstance(res, dict):
                    mid = res.get("id") or res.get("memory_id")
                    if isinstance(mid, str) and mid.strip():
                        created_ids.append(mid.strip())
            return created_ids
    except Exception as e:
        log.warning("Reflection JSON parse/store failed: %s", e, exc_info=True)

    if not allow_fallback_chunking:
        return created_ids

    try:
        for chunk in fallback_chunk_reflection(text):
            res = store_memory(content=chunk)
            if isinstance(res, dict):
                mid = res.get("id") or res.get("memory_id")
                if isinstance(mid, str) and mid.strip():
                    created_ids.append(mid.strip())
    except Exception as e:
        log.warning("Memory storage fallback failed: %s", e, exc_info=True)

    return created_ids


def delete_written_memories(memory_ids: List[str]) -> None:
    for mid in memory_ids:
        try:
            delete_memory(mid)
        except Exception:
            continue
