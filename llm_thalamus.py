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
from typing import Callable, Dict, List, Optional

import requests

from memory_retrieval import query_memories, query_episodic
from memory_storage import store_semantic, store_episodic

# ---------------------------------------------------------------------------
# Config path detection
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
local_cfg = BASE_DIR / "config" / "config.json"
system_cfg = Path("/etc/thalamus/config.json")

if local_cfg.exists():
    CONFIG_PATH = local_cfg
elif system_cfg.exists():
    CONFIG_PATH = system_cfg
else:
    raise FileNotFoundError(
        f"Missing config.json (tried {local_cfg} and {system_cfg})"
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ThalamusConfig:
    project_name: str = "llm-thalamus"
    default_user_id: str = "default"

    # LLM / Ollama
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"

    # Memory behaviour
    max_memory_results: int = 20
    enable_reflection: bool = True

    # Short-term conversation context (in-RAM rolling window)
    short_term_max_messages: int = 0  # 0 = disabled

    # Agent / tools behaviour (reserved for future UI-directed tools)
    tools: Dict[str, dict] = dataclasses.field(default_factory=dict)
    max_tool_steps: int = 16

    # Logging
    log_level: str = "INFO"
    log_file: Path = BASE_DIR / "logs" / "thalamus.log"

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "ThalamusConfig":
        path = explicit_path or CONFIG_PATH
        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        th_cfg = data.get("thalamus", {})
        emb_cfg = data.get("embeddings", {})
        logging_cfg = data.get("logging", {})
        tools_cfg = data.get("tools", {})

        short_term_cfg = th_cfg.get("short_term_memory", {})
        short_term_max_messages = int(short_term_cfg.get("max_messages", 0))

        return cls(
            project_name=th_cfg.get("project_name", "llm-thalamus"),
            default_user_id=th_cfg.get("default_user_id", "default"),
            ollama_url=emb_cfg.get("ollama_url", "http://localhost:11434"),
            llm_model=th_cfg.get(
                "llm_model",
                os.environ.get("THALAMUS_LLM_MODEL", "qwen2.5:7b"),
            ),
            max_memory_results=int(th_cfg.get("max_memory_results", 20)),
            enable_reflection=bool(th_cfg.get("enable_reflection", True)),
            short_term_max_messages=short_term_max_messages,
            tools=tools_cfg,
            max_tool_steps=int(th_cfg.get("max_tool_steps", 16)),
            log_level=logging_cfg.get("level", "INFO"),
            log_file=Path(logging_cfg.get("file", "./logs/thalamus.log")),
        )


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

    def formatted_block(self) -> str:
        """Return a human-readable block of recent conversation, or empty string."""
        if self.max_messages <= 0 or not self._buffer:
            return ""
        lines: List[str] = []
        for msg in self._buffer:
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

    def retrieve_relevant_memories(self, query: str) -> str:
        try:
            return query_memories(
                query=query,
                user_id=self.user_id,
                k=self.max_k,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Memory retrieval failed: %s", e, exc_info=True
            )
            return ""

    def store_reflection(self, reflection_text: str) -> None:
        text = reflection_text.strip()
        if not text:
            return
        try:
            store_semantic(
                content=text,
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


# ---------------------------------------------------------------------------
# Thalamus – main controller
# ---------------------------------------------------------------------------


class Thalamus:
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

    def set_open_documents(self, documents: Optional[List[Dict[str, str]]]) -> None:
        """
        Replace the current list of open documents.

        Each entry should be a small dict like:
            {"name": "Design doc", "text": "... full or partial content ..."}
        """
        self.open_documents = list(documents or [])

    # ------------------------------------------------------------------ initial chat history from OpenMemory

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

    def process_user_message(self, user_message: str) -> str:
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

        # Store this user turn as an episodic chat memory
        try:
            self.memory.store_chat_turn(
                "user",
                text,
                session_id=session_id,
            )
        except Exception:
            # Chat storage failures should never break the main pipeline
            pass

        # Memory retrieval
        memories_block = self.memory.retrieve_relevant_memories(text)
        if memories_block:
            self._debug_log(
                session_id,
                "memory",
                f"Retrieved memories block:\n{memories_block}",
            )
        else:
            self._debug_log(session_id, "memory", "No relevant memories retrieved.")
        self.events.emit_status("memory", "connected", "idle")

        recent_conversation_block = self.history.formatted_block()

        # LLM call
        try:
            answer = self._call_llm_answer(
                session_id=session_id,
                user_message=text,
                memories_block=memories_block,
                recent_conversation_block=recent_conversation_block,
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

        # Store this assistant turn as an episodic chat memory
        try:
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

        parts: List[str] = []

        # 0) High-level instruction
        parts.append(
            "You are a helpful assistant. Use the information below "
            "(memories, recent conversation, open documents) only as "
            "background context. Do NOT list, quote, or enumerate the "
            "memories or notes back to the user unless they explicitly ask. "
            "Just focus on the User Message and answer naturally and directly.\n\n"
            "In the memories block that follows, the score denotes how \n"
            "relevant the memory is. Pay particular attention to memories\n"
            "with higher scores, as they are more relevant./n"
            "You may safely disregard memories with lower scores, as they/n"
            "are likely to be less relevant./n/n"
            "The user message should be the message you focus on most,/n"
            "in your answer, the memories are just to help you formulate a better /n"
            "answer to the User message:"
        )

        # 1) Current time
        parts.append(f"Current time: {now}")

        # 2) Current user message
        parts.append("User message:\n" + user_message)

        # 3) Top-N memories (N from config), marked as INTERNAL
        n_mem = self.config.max_memory_results
        if memories_block:
            parts.append(
                "INTERNAL MEMORY (do not show directly in your reply):\n"
                f"Top {n_mem} memories about this subject, ranked from most "
                "relevant to least relevant:\n"
                f"{memories_block}"
            )
        else:
            parts.append(
                "INTERNAL MEMORY (do not show directly in your reply):\n"
                f"Top {n_mem} memories about this subject, ranked from most "
                "relevant to least relevant:\n"
                "(no relevant memories found.)"
            )

        # 4) Short-term conversation history (M from config), INTERNAL
        if recent_conversation_block:
            m_hist = self.config.short_term_max_messages
            parts.append(
                "Recent conversation for context "
                "(INTERNAL, not to be repeated verbatim):\n"
                f"Last {m_hist} messages between you and the user:\n"
                f"{recent_conversation_block}"
            )

        # 5) Open documents (if any), INTERNAL
        if self.open_documents:
            doc_lines: List[str] = [
                "Relevant open documents "
                "(INTERNAL context, do not dump them verbatim unless the user "
                "explicitly asks for document content):"
            ]
            for doc in self.open_documents:
                name = (
                    str(doc.get("name"))
                    or str(doc.get("filename"))
                    or "(unnamed document)"
                )
                text = str(doc.get("text") or doc.get("content") or "")
                doc_lines.append(f"{name} containing:\n{text}")
            parts.append("\n".join(doc_lines))

        user_payload = "\n\n".join(parts)

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
        """
        Call the LLM with a minimal inline instruction to produce
        brief notes that might be useful later.
        """
        user_prompt = (
            "Write a few short notes about this exchange that might be useful "
            "to remember for future conversations. Focus on stable facts, "
            "projects, decisions, or long-term preferences. Do not include "
            "filler or your internal reasoning.\n"
            "Write compact, plain-text notes.\n\n"
            "User message:\n"
            f"{user_message}\n\n"
            "Assistant reply:\n"
            f"{assistant_message}\n"
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
# Ollama client
# ---------------------------------------------------------------------------


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: List[Dict[str, str]], timeout: int = 600) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content", "")
        if not isinstance(content, str):
            content = str(content)
        return content


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
