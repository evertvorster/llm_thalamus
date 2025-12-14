# llm_thalamus_internal/context.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import logging
import re
import json

from memory_retrieval import query_memories
from memory_storage import store_memory, store_episodic


# ---------------------------------------------------------------------------
# Short-term conversation history (in-RAM)
# ---------------------------------------------------------------------------


class ConversationHistory:
    """Rolling window of recent chat messages for short-term context."""

    def __init__(self, max_messages: int) -> None:
        # max_messages counts individual messages (user or assistant).
        # If <= 0, history is effectively disabled.
        self.max_messages = max_messages
        self._buffer: List[Dict[str, str]] = []

    def add(self, role: str, text: str) -> None:
        if self.max_messages <= 0:
            return
        self._buffer.append({"role": role, "text": text})
        # Trim from the front if we exceed capacity
        overflow = len(self._buffer) - self.max_messages
        if overflow > 0:
            self._buffer = self._buffer[overflow:]

    def formatted_block(self, limit: Optional[int] = None) -> str:
        """
        Return a human-readable block of recent conversation, or empty string.

        If `limit` is provided and > 0, only the last `limit` messages are
        included. Otherwise, the entire buffer (up to max_messages) is used.
        """
        if self.max_messages <= 0 or not self._buffer:
            return ""
        if limit is not None and limit <= 0:
            return ""
        if limit is not None and limit > 0:
            msgs = self._buffer[-limit:]
        else:
            msgs = self._buffer

        lines: List[str] = []
        for msg in msgs:
            role = msg.get("role", "unknown").capitalize()
            text = msg.get("text", "")
            lines.append(f"{role}: {text}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Memory wrapper
# ---------------------------------------------------------------------------


class MemoryModule:
    def __init__(self, user_id: str, max_k: int) -> None:
        self.user_id = user_id
        self.max_k = max_k

    def retrieve_relevant_memories(self, query: str, k: Optional[int] = None) -> str:
        """
        Retrieve up to `k` relevant memories for the given query.

        If k is None, fall back to this module's max_k (from config.max_memory_results).
        """
        try:
            effective_k = self.max_k if k is None else int(k)
            if effective_k <= 0:
                return ""
            return query_memories(
                query=query,
                k=effective_k,
            )
        except Exception as e:
            logging.getLogger("thalamus").exception(
                "Memory retrieval failed: %s", e
            )
            return ""

    def store_reflection(
        self,
        reflection_text: str,
        *,
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Store reflection output as structured memory writes when available.

        Preferred format
        ----------------
        If the reflection output contains a fenced JSON block:

            ```json
            {"memory_writes": [ ... ]}
            ```

        then we parse it and store each memory item independently, injecting
        `session_id` and `timestamp` into each item's metadata. Anything outside
        the JSON block is ignored for storage purposes.

        Fallback
        --------
        If no parseable JSON block is present, we fall back to the previous
        behavior: split the reflection output on blank lines and store each
        chunk as a plain memory item.
        """
        text = (reflection_text or "").strip()
        if not text:
            return

        def _extract_last_json_fence(s: str) -> Optional[str]:
            # Capture the *last* ```json ... ``` fenced block (case-insensitive).
            blocks = re.findall(r"```json\s*(.*?)\s*```", s, flags=re.DOTALL | re.IGNORECASE)
            return blocks[-1] if blocks else None

        ts = timestamp or datetime.utcnow().isoformat(timespec="seconds") + "Z"

        # 1) Preferred: structured memory writes from a JSON fenced block
        try:
            fenced = _extract_last_json_fence(text)
            if fenced:
                payload = json.loads(fenced)
                writes = payload.get("memory_writes")
                if isinstance(writes, list):
                    for item in writes:
                        if not isinstance(item, dict):
                            continue

                        content = (item.get("content") or "").strip()
                        if not content:
                            continue

                        tags = item.get("tags") or []
                        if not isinstance(tags, list):
                            tags = []

                        metadata = item.get("metadata") or {}
                        if not isinstance(metadata, dict):
                            metadata = {}

                        # Inject per-turn context (do not overwrite if already present)
                        metadata.setdefault("session_id", session_id)
                        metadata.setdefault("timestamp", ts)

                        store_memory(
                            content=content,
                            tags=tags,
                            metadata=metadata,
                                    )
                    return  # do not fall back if we successfully handled a writes list
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Reflection JSON parse/store failed: %s", e, exc_info=True
            )

        # 2) Fallback: legacy chunking behavior
        try:
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            chunks = [
                chunk.strip()
                for chunk in re.split(r"\n\s*\n+", normalized)
                if chunk.strip()
            ]
            for chunk in chunks:
                store_memory(
                    content=chunk,
                    )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Memory storage failed: %s", e, exc_info=True
            )

    def store_chat_turn(
        self,
        role: str,
        text: str,
        *,
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Store a single chat turn into OpenMemory as an episodic-style memory.

        We tag these memories with "chat" so they can be retrieved separately
        from other episodic memories, and include minimal metadata so that
        downstream consumers can reconstruct who said what and when.

        This is intentionally lightweight and append-only; OpenMemory is
        responsible for any longer-term decay / consolidation.
        """
        content = (text or "").strip()
        if not content:
            return

        ts = timestamp or datetime.utcnow().isoformat(timespec="seconds") + "Z"

        metadata = {
            "kind": "chat_turn",
            "role": role,
            "session_id": session_id,
            "timestamp": ts,
        }

        try:
            store_episodic(
                content=content,
                tags=["chat"],
                metadata=metadata,
                date=ts,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Chat memory storage failed: %s", e, exc_info=True
            )
