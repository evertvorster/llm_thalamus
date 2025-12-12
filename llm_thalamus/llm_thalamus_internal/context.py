# llm_thalamus_internal/context.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import logging
import re

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
                user_id=self.user_id,
                k=effective_k,
            )
        except Exception as e:
            logging.getLogger("thalamus").exception(
                "Memory retrieval failed: %s", e
            )
            return ""

    def store_reflection(self, reflection_text: str) -> None:
        """Store reflection output as separate memory chunks.

        The reflection call may return multiple notes separated by blank lines.
        We split on blank lines and store each chunk as its own memory item,
        relying on OpenMemory's automatic classification. In future we may
        enrich this with per-chunk metadata.
        """
        text = reflection_text.strip()
        if not text:
            return

        try:
            # Normalise newlines and split on blank lines
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            chunks = [
                chunk.strip()
                for chunk in re.split(r"\n\s*\n+", normalized)
                if chunk.strip()
            ]
            if not chunks:
                return

            for chunk in chunks:
                store_memory(
                    content=chunk,
                    user_id=self.user_id,
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
                user_id=self.user_id,
                tags=["chat"],
                metadata=metadata,
                date=ts,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Chat memory storage failed: %s", e, exc_info=True
            )
