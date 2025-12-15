from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from llm_thalamus_internal.prompts import load_prompt_template

# BASE_DIR should match the project root where config/ and prompt files live.
# llm_thalamus.py sits one level above this internal package, so we go up one.
BASE_DIR = Path(__file__).resolve().parent.parent


def call_llm_answer(
    thalamus,
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
    Implementation of the LLM 'answer' call, extracted from Thalamus._call_llm_answer.

    Uses:
      - thalamus.open_documents
      - thalamus._get_call_config(...)
      - thalamus.logger
      - thalamus._debug_log(...)
      - thalamus.ollama.chat(...)
    """
    now = datetime.now().isoformat(timespec="seconds")

    # Open documents: index + full contents
    open_docs_index = ""
    open_docs_full = ""
    if thalamus.open_documents:
        # Normalise documents into (name, text) pairs first
        doc_items: List[tuple[str, str]] = []
        for d in thalamus.open_documents:
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

    # Per-tag memories (optional): used when the answer prompt contains
    # placeholders like __MEMORIES_BLOCK_SEMANTIC__. If not provided, these
    # placeholders will be populated with a standard empty message.
    def _mblock(sector: str) -> str:
        if memories_by_sector and isinstance(memories_by_sector, dict):
            val = memories_by_sector.get(sector, "")
            if isinstance(val, str) and val.strip():
                return val
        return f"(no {sector} memories found.)"

    def _mlim(sector: str) -> int:
        if memory_limits_by_sector and isinstance(memory_limits_by_sector, dict):
            try:
                v = memory_limits_by_sector.get(sector, 0)
                return int(v) if v is not None else 0
            except Exception:
                return 0
        return 0


    # Load template and fill tokens
    template = load_prompt_template(
        "answer",
        thalamus._get_call_config("answer"),
        BASE_DIR,
        logger=thalamus.logger,
    )
    if template:
        user_payload = (
            template.replace("__NOW__", now)
            .replace("__OPEN_DOCUMENTS_INDEX__", open_docs_index)
            .replace("__OPEN_DOCUMENTS_FULL__", open_docs_full)
            .replace("__MEMORY_LIMIT__", str(memory_limit))
            .replace("__MEMORIES_BLOCK__", memories_for_template)
            .replace("__MEMORY_LIMIT_REFLECTIVE__", str(_mlim("reflective")))
            .replace("__MEMORIES_BLOCK_REFLECTIVE__", _mblock("reflective"))
            .replace("__MEMORY_LIMIT_SEMANTIC__", str(_mlim("semantic")))
            .replace("__MEMORIES_BLOCK_SEMANTIC__", _mblock("semantic"))
            .replace("__MEMORY_LIMIT_PROCEDURAL__", str(_mlim("procedural")))
            .replace("__MEMORIES_BLOCK_PROCEDURAL__", _mblock("procedural"))
            .replace("__MEMORY_LIMIT_EPISODIC__", str(_mlim("episodic")))
            .replace("__MEMORIES_BLOCK_EPISODIC__", _mblock("episodic"))
            .replace("__MEMORY_LIMIT_EMOTIONAL__", str(_mlim("emotional")))
            .replace("__MEMORIES_BLOCK_EMOTIONAL__", _mblock("emotional"))
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

    thalamus._debug_log(
        session_id,
        "llm_answer_prompt",
        f"User payload sent to LLM:\n{user_payload}",
    )

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": user_payload}
    ]

    content = thalamus.ollama.chat(messages)
    if not isinstance(content, str):
        content = str(content)

    thalamus._debug_log(
        session_id,
        "llm_answer_raw",
        f"Final answer received from LLM:\n{content}",
    )
    return content



def call_llm_reflection(
    thalamus,
    session_id: str,
    user_message: str,
    assistant_message: str,
    memories_by_sector: Optional[Dict[str, str]] = None,
    memory_limits_by_sector: Optional[Dict[str, int]] = None,
) -> str:
    """Implementation of the LLM 'reflection' call.

    Uses:
      - thalamus.config
      - thalamus.history
      - thalamus._get_call_config(...)
      - thalamus.logger
      - thalamus._debug_log(...)
      - thalamus.ollama.chat(...)
    """
    now = datetime.now().isoformat(timespec="seconds")

    # Determine how many recent messages to include for the reflection call.
    reflection_call_cfg = thalamus.config.calls.get("reflection")
    global_max = thalamus.config.short_term_max_messages

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

    recent_conversation_block = thalamus.history.formatted_block(
        limit=reflection_history_limit
    )

    def _mblock(sector: str) -> str:
        if memories_by_sector and isinstance(memories_by_sector, dict):
            val = memories_by_sector.get(sector, "")
            if isinstance(val, str) and val.strip():
                return val
        return f"(no {sector} memories found.)"

    def _mlim(sector: str) -> int:
        if memory_limits_by_sector and isinstance(memory_limits_by_sector, dict):
            try:
                v = memory_limits_by_sector.get(sector, 0)
                return int(v) if v is not None else 0
            except Exception:
                return 0
        return 0

    # Prefer an external template if available; fall back to a minimal prompt.
    template = load_prompt_template(
        "reflection",
        thalamus._get_call_config("reflection"),
        BASE_DIR,
        logger=thalamus.logger,
    )

    if template:
        user_prompt = (
            template
            .replace("__NOW__", now)
            .replace("__RECENT_CONVERSATION_BLOCK__", recent_conversation_block)
            .replace("__USER_MESSAGE__", user_message)
            .replace("__ASSISTANT_MESSAGE__", assistant_message)
            # Sector blocks (optional; only meaningful if the template contains these placeholders)
            .replace("__MEMORY_LIMIT_REFLECTIVE__", str(_mlim("reflective")))
            .replace("__MEMORIES_BLOCK_REFLECTIVE__", _mblock("reflective"))
            .replace("__MEMORY_LIMIT_SEMANTIC__", str(_mlim("semantic")))
            .replace("__MEMORIES_BLOCK_SEMANTIC__", _mblock("semantic"))
            .replace("__MEMORY_LIMIT_PROCEDURAL__", str(_mlim("procedural")))
            .replace("__MEMORIES_BLOCK_PROCEDURAL__", _mblock("procedural"))
            .replace("__MEMORY_LIMIT_EPISODIC__", str(_mlim("episodic")))
            .replace("__MEMORIES_BLOCK_EPISODIC__", _mblock("episodic"))
            .replace("__MEMORY_LIMIT_EMOTIONAL__", str(_mlim("emotional")))
            .replace("__MEMORIES_BLOCK_EMOTIONAL__", _mblock("emotional"))
        )
    else:
        user_prompt = (
            "Reflection prompt template not found.\n"
            "Please ensure config/prompt_reflection.txt is installed.\n\n"
            f"Current time: {now}\n\n"
            f"Human: {user_message}\n"
            f"Assistant: {assistant_message}\n\n"
            f"Recent conversation:\n{recent_conversation_block}\n"
        )

    thalamus._debug_log(
        session_id,
        "llm_reflection_prompt",
        f"User payload for reflection:\n{user_prompt}",
    )

    messages = [{"role": "user", "content": user_prompt}]
    content = thalamus.ollama.chat(messages)
    if not isinstance(content, str):
        content = str(content)
    return content

