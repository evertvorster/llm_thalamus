#!/usr/bin/env python3
"""
llm_thalamus – simplified, single-threaded controller / message router.

For each user message, Thalamus:

- Retrieves relevant memories from OpenMemory.
- Builds a thin prompt that includes:
  - Current time
  - User message
  - Top-N memories (INTERNAL context)
  - Last-M conversation messages (in-RAM short-term context)
  - Any open documents (INTERNAL context)
- Calls the local Ollama LLM for an answer.
- Optionally calls the LLM again for a reflection pass to store notes.

It exposes a small event API for the UI:
- on_chat_message(role, text)
- on_status_update(component, state, detail)
- on_thalamus_control_entry(label, raw_text)
- on_session_started()
- on_session_ended()
"""

from __future__ import annotations

import dataclasses
import json
import re
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from memory_retrieval import query_memories_by_sector_blocks
from llm_thalamus_internal.llm_client import OllamaClient
from llm_thalamus_internal.context import MemoryModule
from llm_thalamus_internal.config import CallConfig, ThalamusConfig
from llm_thalamus_internal.prompts import load_prompt_template
from llm_thalamus_internal import message_history
from llm_thalamus_internal.llm_calls import call_llm_answer, call_llm_reflection, call_llm_memory_query

class FileBackedHistory:
    """
    Compatibility adapter for legacy code paths that expect:
      - thalamus.history.formatted_block(...)
      - thalamus.history.add(...)

    Backed by the JSONL message history file.
    """

    def formatted_block(self, limit: int = 20) -> str:
        # Same format the prompts expect: "role: content"
        return message_history.format_for_prompt(limit)

    def add(self, role: str, content: str) -> None:
        message_history.append_message(role, content)


# =============================================================================
# PUBLIC API NOTICE
#
# External code (UI, tools, scripts) should only import and use:
#
#     from llm_thalamus import Thalamus
#
# The methods considered stable are:
#     Thalamus.process_user_message()
#     Thalamus.emit_initial_chat_history()
#     Thalamus.set_open_documents()
#
# Everything else in this file is internal implementation detail and may
# change as we refactor llm-thalamus into smaller modules.
# =============================================================================

# ---------------------------------------------------------------------------
# Base directory (used for resolving relative prompt template paths)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# NOTE:
# CallConfig and ThalamusConfig now live in llm_thalamus_internal.config.
# They are imported at the top of this file and used throughout Thalamus.



# ---------------------------------------------------------------------------
# Simple event bus
# ---------------------------------------------------------------------------


class ThalamusEvents:
    def __init__(self) -> None:
        # MUST use these names so the UI can hook into them
        self.on_chat_message: Optional[Callable[[str, str], None]] = None
        self.on_status_update: Optional[Callable[[str, str, Optional[str]], None]] = None
        self.on_thalamus_control_entry: Optional[Callable[[str, str], None]] = None
        self.on_session_started: Optional[Callable[[], None]] = None
        self.on_session_ended: Optional[Callable[[], None]] = None

    def emit_chat(self, role: str, text: str) -> None:
        if self.on_chat_message:
            self.on_chat_message(role, text)

    def emit_status(self, component: str, state: str, detail: Optional[str] = None) -> None:
        if self.on_status_update:
            self.on_status_update(component, state, detail)

    def emit_control_entry(self, label: str, raw_text: str) -> None:
        if self.on_thalamus_control_entry:
            self.on_thalamus_control_entry(label, raw_text)

    def emit_session_started(self) -> None:
        if self.on_session_started:
            self.on_session_started()

    def emit_session_ended(self) -> None:
        if self.on_session_ended:
            self.on_session_ended()


# ---------------------------------------------------------------------------
# Short-term conversation history & memory wrapper
#
# Implementations now live in llm_thalamus_internal.context:
# - ConversationHistory
# - MemoryModule
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Thalamus – main controller
# ---------------------------------------------------------------------------


class Thalamus:
    """
    PUBLIC API FACADE

    The Thalamus class is the stable entrypoint used by the UI and any
    external automation. Only these methods are considered public:

        - process_user_message(user_message, open_documents=None)
        - emit_initial_chat_history(k=10)
        - set_open_documents(documents)

    All other methods on this class (and everything else in this module)
    are internal implementation detail and may change as we refactor
    llm-thalamus into smaller modules.
    """

    def __init__(self, config: Optional[ThalamusConfig] = None) -> None:
        self.config = config or ThalamusConfig.load()

        self.events = ThalamusEvents()
        self.logger = logging.getLogger("thalamus")
        self._setup_logging()

        self.ollama = OllamaClient(
            base_url=self.config.ollama_url,
            model=self.config.llm_model,
        )
        self.memory = MemoryModule(
            user_id=self.config.default_user_id,
            max_k=self.config.max_memory_results,
        )

        # Open documents that the UI can register for inclusion in prompts.
        self.open_documents: List[Dict[str, str]] = []

        # Short-term conversation history
        # Chat history is persisted to JSONL via llm_thalamus_internal.message_history

        # Compatibility history adapter (file-backed)
        self.history = FileBackedHistory()

        self.last_user_message: Optional[str] = None
        self.last_assistant_message: Optional[str] = None

        # Initial status for UI
        self.events.emit_status("thalamus", "connected", "idle")
        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("memory", "connected", "idle")

    # ------------------------------------------------------------------ open document management
    # ------------------------------------------------------------------ Call config / prompt loading helpers

    def _get_call_config(self, name: str) -> CallConfig:
        """
        Return the CallConfig for a given call name.

        If the call isn't configured, we return a neutral default CallConfig
        so callers don't have to guard against None.
        """
        cfg = self.config.calls.get(name)
        if cfg is None:
            # Neutral defaults: everything enabled, no explicit limits.
            return CallConfig()
        return cfg

    # NOTE:
    # Prompt template loading is now handled by
    # llm_thalamus_internal.prompts.load_prompt_template.
    # Thalamus calls that helper instead of having a local method.

    # ------------------------------------------------------------------ open document management


    def _format_recent_messages_for_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Format a list of message dicts into the prompt's Conversation history block."""
        if not messages:
            return ""

        lines: List[str] = []
        for m in messages:
            role = str(m.get("role", ""))
            content = str(m.get("content", ""))
            if not role or not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    def set_open_documents(self, documents: Optional[List[Dict[str, str]]]) -> None:
        """
        Replace the current list of open documents.

        Each entry should be a small dict like:
            {"name": "Design doc", "text": "... full or partial content ..."}
        """
        self.open_documents = list(documents or [])

    # ------------------------------------------------------------------ initial chat history from OpenMemory (PUBLIC)

    def emit_initial_chat_history(self, k: int = 10) -> None:
        """
        Emit the last k chat messages from the persisted message history file.

        This is used by the UI to warm up the chat pane on connect.
        """
        try:
            msgs = message_history.get_last_messages(k)
        except Exception as e:
            self.logger.warning("Initial chat history read failed: %s", e, exc_info=True)
            return

        if not msgs:
            return

        for m in msgs:
            role = str(m.get("role", ""))
            content = str(m.get("content", ""))
            if not content:
                continue
            self.events.emit_chat(role, content)

    # ------------------------------------------------------------------ public API


    def _get_memories_by_sector_for_call(
        self,
        call_cfg: Optional[CallConfig],
        *,
        query_text: str,
    ) -> tuple[Optional[Dict[str, str]], Optional[Dict[str, int]]]:
        """Return (memories_by_sector, memory_limits_by_sector) for a given call config.

        If disabled or not configured, returns (None, None).
        """
        if not call_cfg:
            return None, None

        if not getattr(call_cfg, "use_memories", False):
            return None, None

        limits = getattr(call_cfg, "memory_limits_by_sector", None)
        if not limits:
            return None, None

        try:
            blocks = query_memories_by_sector_blocks(
                query_text,
                limits_by_sector=limits,
                candidate_multiplier=2,
            )
            return blocks, limits
        except Exception as e:
            self.logger.warning("Per-sector memory retrieval failed: %s", e, exc_info=True)
            return None, limits

    def process_user_message(
        self,
        user_message: str,
        open_documents: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        text = user_message.strip()
        if not text:
            return ""

        session_id = self._new_session_id()
        self.events.emit_session_started()

        # Indicate busy states to UI
        self.events.emit_status("thalamus", "busy", f"session {session_id}")
        self.events.emit_status("llm", "busy", "answering")
        self.events.emit_status("memory", "busy", "retrieving")

        # From the intelligence's perspective this is a message from the human.
        self.events.emit_chat("human", text)
        self._debug_log(session_id, "pipeline", f"Human message received:\n{text}")

        # Memory retrieval – use per-call limit if provided
        answer_call_cfg = self.config.calls.get("answer")
        global_k = self.config.max_memory_results

        if not answer_call_cfg or answer_call_cfg.max_memories is None:
            answer_memory_limit = global_k
        else:
            try:
                answer_memory_limit = int(answer_call_cfg.max_memories)
            except (TypeError, ValueError):
                answer_memory_limit = global_k
            if answer_memory_limit > global_k:
                answer_memory_limit = global_k
            elif answer_memory_limit < 0:
                answer_memory_limit = 0

        # Determine how many recent messages to include for the answer call.
        answer_call_cfg = self.config.calls.get("answer")
        global_max = self.config.short_term_max_messages

        if global_max <= 0:
            answer_history_limit = 0
        elif not answer_call_cfg or answer_call_cfg.max_messages is None:
            answer_history_limit = global_max
        else:
            try:
                answer_history_limit = int(answer_call_cfg.max_messages)
            except (TypeError, ValueError):
                answer_history_limit = global_max
            if answer_history_limit > global_max:
                answer_history_limit = global_max
            elif answer_history_limit < 0:
                answer_history_limit = 0

        recent_msgs = message_history.get_last_messages(answer_history_limit)
        recent_conversation_block = self._format_recent_messages_for_prompt(recent_msgs)

        # Open documents supplied by the caller (typically the UI).
        # If None, we leave any existing self.open_documents unchanged.
        if open_documents is not None:
            self.set_open_documents(open_documents)

        # Refine the OpenMemory retrieval query using short-term context (optional).
        refined_query = call_llm_memory_query(
            self,
            session_id=session_id,
            user_message=text,
            recent_conversation_block=recent_conversation_block,
            history_message_limit=answer_history_limit,
        )
        if refined_query != text:
            self._debug_log(
                session_id,
                "memory_query",
                f"Refined memory query: {refined_query}",
            )

        # Retrieve memories using the refined query (falls back to user message if refinement fails).
        memories_block = self.memory.retrieve_relevant_memories(
            refined_query,
            k=answer_memory_limit,
        )
        if memories_block:
            self._debug_log(
                session_id,
                "memory",
                f"Retrieved memories block:\n{memories_block}",
            )
        else:
            self._debug_log(session_id, "memory", "No relevant memories retrieved.")
        self.events.emit_status("memory", "connected", "idle")

        # Log what will actually be seen by the LLM as open_documents
        if self.open_documents:
            self._debug_log(
                session_id,
                "open_documents_effective",
                "Effective open_documents before LLM call:\n"
                + "\n".join(
                    f"- {d.get('name') or d.get('filename')}: "
                    f"{(d.get('text') or d.get('content') or '')[:160]}..."
                    for d in self.open_documents
                ),
            )
        else:
            self._debug_log(
                session_id,
                "open_documents_effective",
                "No open_documents set before LLM call.",
            )

        # Per-sector memory retrieval (optional, controlled by call config)
        memories_by_sector, memory_limits_by_sector = self._get_memories_by_sector_for_call(
            answer_call_cfg,
            query_text=refined_query,
        )

        # LLM call
        try:
            answer = self._call_llm_answer(
                session_id=session_id,
                user_message=text,
                memories_block=memories_block,
                recent_conversation_block=recent_conversation_block,
                history_message_limit=answer_history_limit,
                memory_limit=answer_memory_limit,
                memories_by_sector=memories_by_sector,
                memory_limits_by_sector=memory_limits_by_sector,
)
        except Exception as e:
            self.logger.exception("LLM answer call failed")
            self.events.emit_status("llm", "error", str(e))
            self.events.emit_status("thalamus", "error", "LLM call failed")
            self.events.emit_session_ended()
            raise

        # Update last-turn markers and rolling history
        self.last_user_message = text
        self.last_assistant_message = answer
        # In our identity model:
        # - "human" is the person at the keyboard
        # - "you" is the intelligence
        message_history.append_message("human", text)
        message_history.append_message("you", answer)

        self.events.emit_chat("you", answer)
        self._debug_log(session_id, "llm_answer", f"Intelligence answer:\n{answer}")

        # Chat turns are persisted to the JSONL message history file (not OpenMemory).
        # The append calls above are intentionally best-effort and do not affect the main pipeline.

        # LLM finished answering
        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("thalamus", "connected", "idle")

        # Reflection
        if self.config.enable_reflection:
            try:
                self.events.emit_status("thalamus", "busy", "reflecting")
                self.events.emit_status("llm", "busy", "reflecting")

                # Per-sector memory retrieval for reflection (optional, controlled by call config)
                reflection_call_cfg = self.config.calls.get("reflection")
                memories_by_sector_reflection, memory_limits_by_sector_reflection = self._get_memories_by_sector_for_call(
                    reflection_call_cfg,
                    query_text=refined_query,
                )

                reflection = self._call_llm_reflection(
                    session_id=session_id,
                    user_message=text,
                    assistant_message=answer,
                    memories_by_sector=memories_by_sector_reflection,
                    memory_limits_by_sector=memory_limits_by_sector_reflection,
                )
                self._debug_log(
                    session_id,
                    "reflection",
                    f"Reflection output:\n{reflection}",
                )
                self.memory.store_reflection(reflection, session_id=session_id)
            except Exception as e:
                self.logger.warning("Reflection step failed: %s", e, exc_info=True)
            finally:
                self.events.emit_status("llm", "connected", "idle")
                self.events.emit_status("thalamus", "connected", "idle")

        self.events.emit_session_ended()
        return answer

    # ------------------------------------------------------------------ internals

    def _setup_logging(self) -> None:
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            handlers=[
                logging.FileHandler(self.config.log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _new_session_id(self) -> str:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        rand = uuid.uuid4().hex[:8]
        return f"session-{ts}-{rand}"

    def _debug_log(self, session_id: str, label: str, text: str) -> None:
        """
        Emit a machine-readable block to the UI log stream.

        Format:
        @@@ THALAMUS_BLOCK START ts=... session=... label=...
        [session-...] label
        <existing body...>
        @@@ THALAMUS_BLOCK END session=... label=...

        The UI can filter reliably by parsing only the START line and then treating
        everything until END as the block body.
        """
        from datetime import datetime, timezone

        # Keep timestamps stable and machine-readable (UTC, ISO 8601)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Keep the original header exactly as before
        header = f"[{session_id}] {label}"

        # Machine-readable envelope (single-line K/V pairs)
        start = f"@@@ THALAMUS_BLOCK START ts={ts} session={session_id} label={label}"
        end = f"@@@ THALAMUS_BLOCK END session={session_id} label={label}"

        # Preserve existing body formatting
        body = f"{start}\n{header}\n{text.rstrip()}\n{end}"

        # Emit to the UI (unchanged transport)
        self.events.emit_control_entry(label, body)

    def _call_llm_answer(
        self,
        session_id: str,
        user_message: str,
        memories_block: str,
        recent_conversation_block: str,
        history_message_limit: int,
        memory_limit: int,
        memories_by_sector: Optional[Dict[str, str]] = None,
        memory_limits_by_sector: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        Delegate to llm_thalamus_internal.llm_calls.call_llm_answer.
        """
        return call_llm_answer(
            self,
            session_id=session_id,
            user_message=user_message,
            memories_block=memories_block,
            recent_conversation_block=recent_conversation_block,
            history_message_limit=history_message_limit,
            memory_limit=memory_limit,
            memories_by_sector=memories_by_sector,
            memory_limits_by_sector=memory_limits_by_sector,
)

    def _call_llm_reflection(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        memories_by_sector: Optional[Dict[str, str]] = None,
        memory_limits_by_sector: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        Delegate to llm_thalamus_internal.llm_calls.call_llm_reflection.
        """
        return call_llm_reflection(
            self,
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            memories_by_sector=memories_by_sector,
            memory_limits_by_sector=memory_limits_by_sector,
)



# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    _ = argv
    th = Thalamus()
    print("llm_thalamus CLI – type messages, Ctrl+C to exit.\n")

    try:
        while True:
            try:
                user_msg = input("you> ")
            except EOFError:
                break
            if not user_msg.strip():
                continue
            answer = th.process_user_message(user_msg)
            print(f"ai> {answer}\n")
    except KeyboardInterrupt:
        print("\nExiting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())