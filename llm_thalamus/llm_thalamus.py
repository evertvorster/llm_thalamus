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
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from paths import get_user_config_path, get_log_dir
from memory_retrieval import query_memories, query_episodic
from memory_storage import store_semantic, store_episodic
from llm_thalamus_internal.llm_client import OllamaClient
from llm_thalamus_internal.context import ConversationHistory, MemoryModule
from llm_thalamus_internal.config import CallConfig, ThalamusConfig

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
# Config path detection
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Let paths.py decide dev vs installed and copy a template on first run.
CONFIG_PATH = get_user_config_path()


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
        self.history = ConversationHistory(self.config.short_term_max_messages)

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

    def _load_prompt_template(self, call_name: str) -> Optional[str]:
        """
        Load the prompt template text for a given call from disk, if configured.

        Resolution rules:
        - Use self.config.calls[call_name].prompt_file if set.
        - If the path is relative, treat it as relative to BASE_DIR.
        - On any failure, log and return None (callers can fall back to
          inline prompts).
        """
        cfg = self._get_call_config(call_name)
        path_str = cfg.prompt_file
        if not path_str:
            return None

        path = Path(path_str)
        if not path.is_absolute():
            # For now, keep it simple: resolve relative to project base.
            # Packaging can later drop in an absolute path if needed.
            path = BASE_DIR / path

        try:
            with path.open("r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            self.logger.warning(
                "Prompt template for call %s not found at %s",
                call_name,
                path,
            )
            return None
        except Exception:
            self.logger.exception(
                "Error loading prompt template for call %s from %s",
                call_name,
                path,
            )
            return None

        return text

    # ------------------------------------------------------------------ open document management

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
        Retrieve a few recent chat-like episodic memories from OpenMemory
        and emit them as a single assistant message to warm up the UI chat.

        This reuses the same retrieval infrastructure used elsewhere.
        The exact tagging/querying strategy can be tuned later.
        """
        try:
            history_block = query_episodic(
                query="recent conversation with the user",
                k=k,
                user_id=self.config.default_user_id,
                tags=["chat"],
            )
        except Exception as e:
            self.logger.warning(
                "Initial chat history retrieval failed: %s", e, exc_info=True
            )
            return

        if not history_block:
            return

        # For now, emit as a single assistant message.
        # Later we can parse this into individual turns if we store them that way.
        self.events.emit_chat("assistant", history_block)

    # ------------------------------------------------------------------ public API

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

        self.events.emit_chat("user", text)
        self._debug_log(session_id, "pipeline", f"User message received:\n{text}")

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

        memories_block = self.memory.retrieve_relevant_memories(
            text,
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

        recent_conversation_block = self.history.formatted_block(
            limit=answer_history_limit
        )

        # Open documents supplied by the caller (typically the UI).
        # If None, we leave any existing self.open_documents unchanged.
        if open_documents is not None:
            self.set_open_documents(open_documents)

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

        # LLM call
        try:
            answer = self._call_llm_answer(
                session_id=session_id,
                user_message=text,
                memories_block=memories_block,
                recent_conversation_block=recent_conversation_block,
                history_message_limit=answer_history_limit,
                memory_limit=answer_memory_limit,
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
        self.history.add("user", text)
        self.history.add("assistant", answer)

        self.events.emit_chat("assistant", answer)
        self._debug_log(session_id, "llm_answer", f"Assistant answer:\n{answer}")

        # Store both user and assistant turns as episodic chat memories,
        # but only AFTER this exchange has been completed.
        try:
            self.memory.store_chat_turn(
                "user",
                text,
                session_id=session_id,
            )
            self.memory.store_chat_turn(
                "assistant",
                answer,
                session_id=session_id,
            )
        except Exception:
            # Chat storage failures should never break the main pipeline
            pass

        # LLM finished answering
        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("thalamus", "connected", "idle")

        # Reflection
        if self.config.enable_reflection:
            try:
                self.events.emit_status("thalamus", "busy", "reflecting")
                self.events.emit_status("llm", "busy", "reflecting")

                reflection = self._call_llm_reflection(
                    session_id=session_id,
                    user_message=text,
                    assistant_message=answer,
                )
                self._debug_log(
                    session_id,
                    "reflection",
                    f"Reflection output:\n{reflection}",
                )
                self.memory.store_reflection(reflection)
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
        header = f"[{session_id}] {label}"
        body = f"{header}\n{text}"
        self.logger.debug(body)
        self.events.emit_control_entry(label, body)

    def _call_llm_answer(
        self,
        session_id: str,
        user_message: str,
        memories_block: str,
        recent_conversation_block: str,
        history_message_limit: int,
        memory_limit: int,
    ) -> str:
        """
        Call the LLM once with:
        - A brief instruction on how to use context.
        - Current time.
        - User message.
        - INTERNAL memories block.
        - INTERNAL recent conversation block.
        - INTERNAL open documents.

        The INTERNAL blocks are for reasoning only and should not be
        listed or quoted back to the user.
        """
        now = datetime.now().isoformat(timespec="seconds")

        # Build dynamic sections, then fill a template-based prompt.

        # Open documents: index + full contents
        open_docs_index = ""
        open_docs_full = ""
        if self.open_documents:
            # Normalise documents into (name, text) pairs first
            doc_items: List[tuple[str, str]] = []
            for d in self.open_documents:
                name = (
                    str(d.get("name"))
                    or str(d.get("filename"))
                    or "(unnamed document)"
                )
                text = str(d.get("text") or d.get("content") or "")
                doc_items.append((name, text))

            index_lines: List[str] = []
            for idx, (name, _text) in enumerate(doc_items, start=1):
                index_lines.append(f"{idx}. {name} (type: text_file)")
            open_docs_index = "\n".join(index_lines)

            full_lines: List[str] = []
            for idx, (name, text) in enumerate(doc_items, start=1):
                full_lines.append(f"===== DOCUMENT {idx} START: {name} =====")
                full_lines.append(text)
                full_lines.append(f"===== DOCUMENT {idx} END: {name} =====\n")
            open_docs_full = "\n".join(full_lines)
        else:
            open_docs_index = "(no open documents in the current Space.)"
            open_docs_full = ""

        # Memories: either real block or placeholder
        if memories_block:
            memories_for_template = memories_block
        else:
            memories_for_template = "(no relevant memories found.)"

        # Chat history: may be empty
        if recent_conversation_block:
            history_for_template = recent_conversation_block
        else:
            history_for_template = "(no recent chat history available.)"

        # Load template and fill tokens
        template = self._load_prompt_template("answer")
        if template:
            user_payload = (
                template.replace("__NOW__", now)
                .replace("__OPEN_DOCUMENTS_INDEX__", open_docs_index)
                .replace("__OPEN_DOCUMENTS_FULL__", open_docs_full)
                .replace("__MEMORY_LIMIT__", str(memory_limit))
                .replace("__MEMORIES_BLOCK__", memories_for_template)
                .replace("__HISTORY_MESSAGE_LIMIT__", str(history_message_limit))
                .replace("__CHAT_HISTORY_BLOCK__", history_for_template)
                .replace("__USER_MESSAGE__", user_message)
            )
        else:
            # Minimal fallback so we don't keep the large inline prompt in code.
            user_payload = (
                f"Current time: {now}\n\n"
                f"User message:\n{user_message}\n\n"
                "Note: answer prompt template not found; "
                "documents, memories, and chat history are omitted."
            )


        self._debug_log(
            session_id,
            "llm_answer_prompt",
            f"User payload sent to LLM:\n{user_payload}",
        )

        messages: List[Dict[str, str]] = [
            {"role": "user", "content": user_payload}
        ]

        content = self.ollama.chat(messages)
        if not isinstance(content, str):
            content = str(content)

        self._debug_log(
            session_id,
            "llm_answer_raw",
            f"Final answer received from LLM:\n{content}",
        )
        return content

    def _call_llm_reflection(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> str:
        now = datetime.now().isoformat(timespec="seconds")

        # Determine how many recent messages to include for the reflection call.
        reflection_call_cfg = self.config.calls.get("reflection")
        global_max = self.config.short_term_max_messages

        if global_max <= 0:
            reflection_history_limit = 0
        elif not reflection_call_cfg or reflection_call_cfg.max_messages is None:
            reflection_history_limit = global_max
        else:
            try:
                reflection_history_limit = int(reflection_call_cfg.max_messages)
            except (TypeError, ValueError):
                reflection_history_limit = global_max
            if reflection_history_limit > global_max:
                reflection_history_limit = global_max
            elif reflection_history_limit < 0:
                reflection_history_limit = 0

        recent_conversation_block = self.history.formatted_block(
            limit=reflection_history_limit
        )
        """
        Call the LLM with a minimal inline instruction to produce
        brief notes that might be useful later.
        """

        # Prefer an external template if available; fall back to the
        # existing inline prompt if not.
        template = self._load_prompt_template("reflection")
        if template:
            # Replace simple tokens with dynamic content. This avoids any
            # brace/format issues while keeping the template as plain text.
            user_prompt = (
                template.replace("__NOW__", now)
                .replace("__RECENT_CONVERSATION_BLOCK__", recent_conversation_block)
                .replace("__USER_MESSAGE__", user_message)
                .replace("__ASSISTANT_MESSAGE__", assistant_message)
            )
        else:
            # Fallback should never be hit now that the template file exists.
            # This prevents the entire massive inline prompt from living in code.
            user_prompt = (
                "Reflection prompt template not found.\n"
                "Please ensure config/prompt_reflection.txt is installed.\n"
                "Dynamic content:\n"
                f"User: {user_message}\n"
                f"Assistant: {assistant_message}\n"
                f"History:\n{recent_conversation_block}\n"
            )


        self._debug_log(
            session_id,
            "llm_reflection_prompt",
            f"User payload for reflection:\n{user_prompt}",
        )

        messages = [
            {"role": "user", "content": user_prompt},
        ]
        return self.ollama.chat(messages)


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
