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

import requests

from paths import get_user_config_path, get_log_dir
from memory_retrieval import query_memories, query_episodic
from memory_storage import store_semantic, store_episodic

# ---------------------------------------------------------------------------
# Config path detection
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Let paths.py decide dev vs installed and copy a template on first run.
CONFIG_PATH = get_user_config_path()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class CallConfig:
    """
    Per-LLM-call configuration.

    For now this is a thin container for limits and feature flags.
    In a later pass we'll also use `prompt_file` to load the actual
    template text from disk.
    """
    prompt_file: Optional[str] = None
    max_memories: Optional[int] = None
    max_messages: Optional[int] = None
    use_memories: bool = True
    use_history: bool = True
    use_documents: bool = True
    flags: Dict[str, Any] = dataclasses.field(default_factory=dict)


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

    # Per-call configuration (answer, reflection, etc.)
    calls: Dict[str, CallConfig] = dataclasses.field(default_factory=dict)

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

        # Log file: use config value if present; otherwise XDG-style via paths.py
        log_file_raw = logging_cfg.get("file")
        if log_file_raw:
            log_file = Path(log_file_raw)
        else:
            log_file = get_log_dir() / "thalamus.log"

        # ----- Per-call configuration -----
        prompts_cfg = data.get("prompts", {})
        calls_cfg_raw = th_cfg.get("calls") or {}
        if not isinstance(calls_cfg_raw, dict):
            calls_cfg_raw = {}

        base_defaults: Dict[str, Any] = {
            "prompt_file": None,
            "max_memories": None,
            "max_messages": None,
            "use_memories": True,
            "use_history": True,
            "use_documents": True,
            "flags": {},
        }

        def build_call(name: str, extra: Optional[Dict[str, Any]] = None) -> CallConfig:
            defaults = dict(base_defaults)
            if extra:
                defaults.update(extra)
            raw = calls_cfg_raw.get(name, {})
            if not isinstance(raw, dict):
                raw = {}
            merged = {**defaults, **raw}
            return CallConfig(
                prompt_file=merged.get("prompt_file"),
                max_memories=merged.get("max_memories"),
                max_messages=merged.get("max_messages"),
                use_memories=bool(merged.get("use_memories", True)),
                use_history=bool(merged.get("use_history", True)),
                use_documents=bool(merged.get("use_documents", True)),
                flags=dict(merged.get("flags") or {}),
            )

        calls: Dict[str, CallConfig] = {
            # Primary answer call: default to existing prompt_answer path
            "answer": build_call(
                "answer",
                {"prompt_file": prompts_cfg.get("answer")},
            ),
            # Reflection call: default to existing prompt_reflection path
            "reflection": build_call(
                "reflection",
                {"prompt_file": prompts_cfg.get("reflection")},
            ),
            # Stubs for future calls – safe no-ops for now
            "space_answer": build_call("space_answer"),
            "space_reflection": build_call("space_reflection"),
            "plan": build_call("plan"),
            "understand": build_call("understand"),
            "execute": build_call("execute"),
        }

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
            calls=calls,
            log_level=logging_cfg.get("level", "INFO"),
            log_file=log_file,
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

        # 0) Current time
        parts.append(f"Current time: {now}")

        # 1) Open documents (if any), INTERNAL
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

            doc_lines: List[str] = [
                "\nRelevant DOCUMENTS (working material):",
                "- These are the actual documents the user may want you to edit, analyse, "
                "summarise, or quote from.",
                "- You MAY quote relevant parts or rewrite sections to satisfy the user's request.",
                "- Avoid dumping the entire document verbatim unless the user clearly asks for it.",
                "- When you refer to a document, use its exact name from the list below.",
                "",
                "Open documents in the current Space:",
            ]

            # Short index of open docs
            for idx, (name, _text) in enumerate(doc_items, start=1):
                doc_lines.append(f"{idx}. {name} (type: text_file)")

            doc_lines.append(
                "\nBelow are the full contents of each open document, wrapped in clear markers.\n"
            )

            # Full contents with loud boundaries
            for idx, (name, text) in enumerate(doc_items, start=1):
                doc_lines.append(f"===== DOCUMENT {idx} START: {name} =====")
                doc_lines.append(text)
                doc_lines.append(f"===== DOCUMENT {idx} END: {name} =====\n")

            doc_lines.append("---- End of documents section -----")
            parts.append("\n".join(doc_lines))

        # 2) Top-N memories (N from config), marked as INTERNAL
        n_mem = self.config.max_memory_results
        if memories_block:
            parts.append(
                "INTERNAL MEMORY (do not show directly in your reply):\n"
                f"Top {n_mem} memories about this subject, scored from most "
                "relevant (20) to least relevant(0).:\n"
                f"{memories_block}"
            )
        else:
            parts.append(
                "INTERNAL MEMORY (do not show directly in your reply):\n"
                f"Top {n_mem} memories about this subject, scored from most "
                "relevant (20) to least relevant(0). :\n"
                "(no relevant memories found.)"
            )
            parts.append("\n  ---- End of memories section -----\n")

        # 3) Short-term conversation history (M from config), INTERNAL
        if recent_conversation_block:
            m_hist = self.config.short_term_max_messages
            parts.append(
                "CHAT HISTORY for CONTEXT (INTERNAL ONLY):\n"
                "These are past messages for reference, not new questions.\n"
                "Use them only to resolve references like 'that issue we discussed earlier'.\n"
                "Do NOT answer these messages again; only answer the latest User message above.\n\n"

                f"Last {m_hist} messages between you and the user:\n"
                f"{recent_conversation_block}"
            )
            parts.append("\n  ---- End of Chat History section -----\n")

        # 4) High-level instruction
        parts.append(
            "You are a helpful digital companion to the user.\n\n"
            "- Older chat turns and memories are HISTORY and exist only to clarify context.\n"
            "- If there is any conflict, ALWAYS follow the latest User message.\n\n"
            "In summary:\n"
            "1) OPEN DOCUMENTS (HIGH PRIORITY, CURRENT SPACE): the actual documents "
            "   the user is working on *right now* in this Space.\n"
            "2) INTERNAL MEMORY: long-term notes about the user or past events.\n"
            "3) HISTORICAL CHAT CONTEXT: recent back-and-forth messages.\n\n"
            "- INTERNAL MEMORY and HISTORICAL CHAT are for your reasoning only. "
            "  Do not list or quote them unless the user explicitly asks.\n"
            "- When answering ANY question about files, code, or documents "
            "  \"in this Space\" or \"in the prompt\", you MUST rely ONLY on the "
            "  'Open documents in the current Space' list above.\n"
            "  If that list conflicts with anything in INTERNAL MEMORY or CHAT HISTORY, "
            "  assume the Open Documents list is correct and ignore the other sources.\n"
            "- OPEN DOCUMENTS are meant to be actively worked on. You may quote, "
            "  summarise, refactor, or transform them as needed to answer the user's request.\n"
            "Now, focus on the User Message and answer it. (shown below as 'User message:') "
        )


        # 5) Current user message
        parts.append("User message:\n" + user_message)


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
        now = datetime.now().isoformat(timespec="seconds")
        recent_conversation_block = self.history.formatted_block()
        """
        Call the LLM with a minimal inline instruction to produce
        brief notes that might be useful later.
        """
        user_prompt = (
            "You are a Memory Architect for an AI companion that uses OpenMemory.\n"
            "\n"
            "OpenMemory organizes memories into 5 sectors mirroring human cognition:\n"
            "\n"
            "1) Episodic – event memories tied to time and context.\n"
            "   Episodic memories MUST include a clear timestamp, either natural language\n"
            "   (\"today\", \"earlier this evening\", \"on YYYY-MM-DD\") or explicit\n"
            "   (\"YYYY-MM-DD HH:MM\").\n"
            "   Examples:\n"
            "   - \"On YYYY-MM-DD, during a late-night debugging session, the user tested\n"
            "      the Space system with two open files.\"\n"
            "   - \"Earlier this evening, the companion misidentified open files and the\n"
            "      user clarified the correct behavior.\"\n"
            "\n"
            "2) Semantic – stable facts and knowledge.\n"
            "   Examples:\n"
            "   - \"The user runs Arch Linux with KDE Plasma on an ASUS ROG system.\"\n"
            "   - \"The user prefers system packages over pip whenever possible.\"\n"
            "\n"
            "3) Procedural – workflows, habits, and routines.\n"
            "   Examples:\n"
            "   - \"The user usually rebuilds and installs via make before testing changes.\"\n"
            "   - \"To debug projects, the user adds detailed logging and inspects logs.\"\n"
            "\n"
            "4) Emotional – feelings and sentiment.\n"
            "   Examples:\n"
            "   - \"The user feels frustrated when tools hide important logs.\"\n"
            "   - \"The user enjoys concise answers unless they request more detail.\"\n"
            "\n"
            "5) Reflective – insights and patterns.\n"
            "   Examples:\n"
            "   - \"The user frequently switches between multiple large projects and\n"
            "      values strong context recall.\"\n"
            "   - \"The companion is becoming an increasingly central tool in the user's\n"
            "      workflow as their personal AI 'brain'.\"\n"
            "\n"
            "YOUR TASK:\n"
            "Take note of the current time and date.\n"
            "Analyze the user message and companion reply below and \n"
            "write memory sentences about this exchange that could still be useful weeks\n"
            "or months from now. You may create memories fitting any of the five sectors.\n"
            "\n"
            "Focus on information that is likely to remain useful, such as:\n"
            "The user's long-term projects or recurring goals\n\n"
            "Stable facts about their system or tools\n\n"
            "Workflows and habits\n\n"
            "Preferences and emotional patterns\n\n"
            "Insights about how the user and companion interact\n\n"
            "Events from THIS session that may matter later, written as episodic and\n\n"
            "  explicitly time-stamped\n"
            "\n\n"
            "When capturing temporary or transient details (like which files were open,\n"
            "errors encountered, or debugging actions), NEVER store them as if they are\n"
            "presently true. Instead, phrase them as episodic past events WITH a timestamp\n"
            "of the current time\n"
            "Example:\n"
            "   \"On YYYY-MM-DD at around HH:MM, the user inspected which Space documents\n"
            "    were being passed through Thalamus during a debugging session.\"\n"
            "\n"
            "Avoid storing:\n"
            "- The current open files as timeless facts\n"
            "- Statements about what the model can or cannot see \"right now\"\n"
            "- Prompt formatting details, debug markers, or ephemeral internal structure\n"
            "- One-off error messages unless they represent a recurring pattern\n"
            "\n"
            "OUTPUT RULES:\n"
            "Use the current time for semantic memories.\n\n"
            "Return ONLY plain-text memory sentences, one per line.\n\n"
            "Put a blank line between memories\n\n"
            "Do NOT label or tag the memories; instead, phrase each memory so the sector is\n"
            "  obvious from the wording.\n\n"
            f"Episodic memories MUST contain the CURRENT time: {now}\n\n"
            "Write as many useful memories as needed.\n"
            "\n"
            "The last few turns of the conversation, added here to give you\n"
            "some context:\n"
            f"{recent_conversation_block}\n\n"
            "The User message that  you must analyze:\n"
            f"{user_message}\n\n"
            "For context, the response of companion, or in other words, YOU:\n"
            "companion reply:\n"
            f"{assistant_message}\n"
            "Apply more consideration to the user message, \n"
            "and only use the companion for context.\n"
            "If the companion did say something truly worth keeping,\n"
            "mention that it was the companion that said it."
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
