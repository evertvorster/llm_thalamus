# llm_thalamus_internal/context.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import logging
import re
import json

from memory_retrieval import query_memories
from memory_storage import store_memory


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
            logging.getLogger("thalamus").exception("Memory retrieval failed: %s", e)
            return ""

    def store_reflection(
        self,
        reflection_text: str,
        *,
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Store reflection output as structured memory writes when available.

        We are intentionally tolerant of slight model formatting drift.

        Preferred format (as instructed in the reflection prompt)
        ---------------------------------------------------------
            ```json
            {"memory_writes": [ ... ]}
            ```

        Also accepted (common drift)
        ----------------------------
        A raw JSON object with the same shape, without fences.
        """
        text = (reflection_text or "").strip()
        if not text:
            return

        log = logging.getLogger("thalamus")
        ts = timestamp or datetime.utcnow().isoformat(timespec="seconds") + "Z"

        def _extract_last_json_fence(s: str) -> Optional[str]:
            blocks = re.findall(r"```json\s*(.*?)\s*```", s, flags=re.DOTALL | re.IGNORECASE)
            return blocks[-1] if blocks else None

        def _coerce_tags(item: Dict[str, object]) -> List[str]:
            """
            Reflection prompt says each memory has:
              - tag: "<single_word_tag>"   (string)
            Some older code expects tags: [ ... ].

            We accept either, but store tags as a list for OpenMemory.
            """
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

        def _parse_payload(s: str) -> Optional[Dict[str, object]]:
            # 1) fenced json (preferred)
            fenced = _extract_last_json_fence(s)
            if fenced:
                return json.loads(fenced)

            # 2) raw json object (drift-tolerant)
            # Only attempt if it looks like JSON; avoid spurious parsing of prose.
            stripped = s.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                return json.loads(stripped)

            return None

        # Structured write path
        try:
            payload = _parse_payload(text)
            if isinstance(payload, dict):
                writes = payload.get("memory_writes")
                if isinstance(writes, list):
                    stored_any = False
                    for item in writes:
                        if not isinstance(item, dict):
                            continue

                        content = (item.get("content") or "").strip()  # type: ignore[union-attr]
                        if not content:
                            continue

                        tags = _coerce_tags(item)

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
                        stored_any = True

                    if stored_any:
                        return  # do not fall back if we stored at least one memory
        except Exception as e:
            log.warning("Reflection JSON parse/store failed: %s", e, exc_info=True)

        # Fallback: legacy chunking behavior (keeps system from 'going silent')
        try:
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            chunks = [
                chunk.strip()
                for chunk in re.split(r"\n\s*\n+", normalized)
                if chunk.strip()
            ]
            for chunk in chunks:
                store_memory(content=chunk)
        except Exception as e:
            log.warning("Memory storage fallback failed: %s", e, exc_info=True)

    # NOTE:
    # We no longer store chat turns into OpenMemory at all.
    # Chat turns are persisted to the JSONL chat history file via the dedicated
    # history module, and are fed into prompts from there.
    def store_chat_turn(
        self,
        role: str,
        text: str,
        *,
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        return
