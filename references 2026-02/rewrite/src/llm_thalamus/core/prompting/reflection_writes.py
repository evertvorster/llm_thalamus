from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def _try_call(obj: object, names: Tuple[str, ...], *args, **kwargs):
    for name in names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    raise AttributeError(f"None of {names} exist on {obj!r}")


def _extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Tolerant extraction: try to parse any JSON object(s) embedded in text.
    Keeps behavior similar to legacy "reflection write" tolerance.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Fast path: whole thing is JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return [obj]
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        pass

    # Slow path: scan for JSON object blocks
    out: List[Dict[str, Any]] = []
    brace = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if brace == 0:
                start = i
            brace += 1
        elif ch == "}":
            if brace > 0:
                brace -= 1
                if brace == 0 and start is not None:
                    chunk = text[start : i + 1]
                    start = None
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            out.append(obj)
                    except Exception:
                        continue
    return out


def _as_reflection_memories(objs: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any], List[str]]]:
    """
    Convert reflection JSON objects into (content, metadata, tags).
    Keeps this file PURE in terms of structure; persistence is delegated to the adapter client.
    """
    memories: List[Tuple[str, Dict[str, Any], List[str]]] = []

    for o in objs:
        # Common reflection schema shapes we’ve seen:
        # - {"content": "...", "metadata": {...}, "tags": [...]}
        # - {"memory": "...", ...}
        # - {"memories": [{"content": ...}, ...]}
        if "memories" in o and isinstance(o["memories"], list):
            for m in o["memories"]:
                if not isinstance(m, dict):
                    continue
                content = str(m.get("content") or m.get("memory") or "").strip()
                if not content:
                    continue
                metadata = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                tags = m.get("tags") if isinstance(m.get("tags"), list) else []
                tags = [str(t) for t in tags if t]
                memories.append((content, dict(metadata), tags))
            continue

        content = str(o.get("content") or o.get("memory") or "").strip()
        if not content:
            continue
        metadata = o.get("metadata") if isinstance(o.get("metadata"), dict) else {}
        tags = o.get("tags") if isinstance(o.get("tags"), list) else []
        tags = [str(t) for t in tags if t]
        memories.append((content, dict(metadata), tags))

    return memories


def store_reflection_text(
    reflection_text: str,
    *,
    user_id: Optional[str] = None,
) -> List[str]:
    """
    Parse reflection output and store memories.

    HARD RULE: persistence must go only through adapters/openmemory/client.py.
    """
    from llm_thalamus.adapters.openmemory import client as om_client

    objs = _extract_json_objects(reflection_text)
    memories = _as_reflection_memories(objs)

    if not memories:
        return []

    uid = user_id or _try_call(om_client, ("get_default_user_id",))

    stored_ids: List[str] = []
    for content, metadata, tags in memories:
        # Try a few canonical adapter method names for adding/storing
        res = _try_call(
            om_client,
            ("store_memory", "add_memory", "add", "create_memory"),
            content,
            user_id=uid,
            metadata=metadata,
            tags=tags,
        )

        # Normalize returned id
        if isinstance(res, dict):
            mid = res.get("id") or res.get("memory_id")
            if mid:
                stored_ids.append(str(mid))
        else:
            # Some adapters return an object with .id
            mid = getattr(res, "id", None)
            if mid:
                stored_ids.append(str(mid))

    return stored_ids


def delete_reflection_memories(
    memory_ids: List[str],
    *,
    user_id: Optional[str] = None,
) -> int:
    """
    Delete memories by id.

    HARD RULE: persistence must go only through adapters/openmemory/client.py.
    """
    from llm_thalamus.adapters.openmemory import client as om_client

    if not memory_ids:
        return 0

    uid = user_id or _try_call(om_client, ("get_default_user_id",))

    deleted = 0
    for mid in memory_ids:
        _try_call(
            om_client,
            ("delete_memory", "delete", "remove_memory", "remove"),
            str(mid),
            user_id=uid,
        )
        deleted += 1

    return deleted
