#!/usr/bin/env python3
"""llm_thalamus_internal.llm_calls

Helper functions that shape and dispatch the actual LLM calls
(answer + reflection). They operate on a Thalamus-like object
(duck-typed) to avoid circular imports: anything with the same
attributes as Thalamus will work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List


def call_llm_answer(
    thalamus,
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
    if thalamus.open_documents:
        doc_items: List[tuple[str, str]] = []
        for d in thalamus.open_documents:
            try:
                doc_id = d.get("id")
                filename = d.get("filename")
                text = d.get("text") or d.get("content") or ""
            except Exception:
                continue

            name = (
                f"{filename} ({doc_id})"
                if filename and doc_id
                else str(filename or doc_id or "(unnamed document)")
            )
            doc_items.append((name, str(text)))

        index_lines: List[str] = []
        for idx, (name, _text) in enumerate(doc_items, start=1):
            index_lines.append(f"{idx}. {name} (type: text_file)")
        open_docs_index = "\n".join(index_lines)

        full_lines: List[str] = []
        for idx, (name, text) in enumerate(doc_items, start=1):
            full_lines.append(f"===== DOCUMENT {idx} START: {name} =====")
            full_lines.append(text)
            full_lines.append(f"===== DOCUMENT {idx} END =====")
        open_docs_full = "\n".join(full_lines)

    # If we have no memories, history, or documents, we still want to
    # pass minimal scaffolding (the instructions + user message).
    # The template is responsible for deciding how to present them.
    answer_call_cfg = thalamus._get_call_config("answer")
    template = thalamus._load_prompt_template("answer")

    # Work out effective limits for memory/history use.
    global_max_messages = thalamus.config.short_term_max_messages
    if global_max_messages <= 0:
        effective_history_limit = 0
    elif answer_call_cfg.max_messages is None:
        effective_history_limit = min(global_max_messages, history_message_limit)
    else:
        try:
            effective_history_limit = int(answer_call_cfg.max_messages)
        except (TypeError, ValueError):
            effective_history_limit = min(global_max_messages, history_message_limit)
        if effective_history_limit > global_max_messages:
            effective_history_limit = global_max_messages
        elif effective_history_limit < 0:
            effective_history_limit = 0

    if answer_call_cfg.max_memories is None:
        effective_memory_limit = memory_limit
    else:
        try:
            effective_memory_limit = int(answer_call_cfg.max_memories)
        except (TypeError, ValueError):
            effective_memory_limit = memory_limit
        if effective_memory_limit < 0:
            effective_memory_limit = 0

    # Optionally trim the blocks according to the effective limits.
    effective_memories_block = memories_block
    if effective_memory_limit <= 0:
        effective_memories_block = ""
    elif effective_memory_limit < memory_limit and memories_block:
        lines = memories_block.splitlines()
        if len(lines) > effective_memory_limit:
            effective_memories_block = "\n".join(lines[:effective_memory_limit])

    effective_history_block = recent_conversation_block
    if effective_history_limit <= 0:
        effective_history_block = ""
    elif recent_conversation_block:
        lines = recent_conversation_block.splitlines()
        # naive: assume each message is a pair of lines "Role: ..." and
        # its content, which is good enough for our current formatting.
        # This avoids having to re-parse messages.
        if len(lines) > (2 * effective_history_limit):
            effective_history_block = "\n".join(lines[-2 * effective_history_limit :])

    # Rebuild the recent conversation block with the effective subset.
    recent_conversation_block = effective_history_block
    memories_block = effective_memories_block

    # Build the dynamic context text blocks.
    context_blocks: List[str] = []

    if memories_block and answer_call_cfg.use_memories:
        context_blocks.append(
            "INTERNAL CONTEXT – RELEVANT MEMORIES\n"
            "These are internal notes about the user and past interactions.\n"
            "They should inform your reasoning, but you should NOT list or\n"
            "quote them back to the user unless explicitly asked.\n"
            "\n"
            f"{memories_block}"
        )

    if recent_conversation_block and answer_call_cfg.use_history:
        context_blocks.append(
            "INTERNAL CONTEXT – RECENT CONVERSATION\n"
            "This is a summary of the most recent turns in the conversation.\n"
            "Use it to stay consistent and avoid repetition, but you should\n"
            "NOT repeat it verbatim.\n"
            "\n"
            f"{recent_conversation_block}"
        )

    if open_docs_index and open_docs_full and answer_call_cfg.use_documents:
        context_blocks.append(
            "INTERNAL CONTEXT – OPEN DOCUMENTS\n"
            "The user currently has the following documents open in the UI.\n"
            "Treat these as authoritative for facts they contain. You may\n"
            "quote or reference them explicitly, but avoid dumping large\n"
            "sections of text.\n"
            "\n"
            "Document index:\n"
            f"{open_docs_index}\n"
            "\n"
            "Document contents:\n"
            f"{open_docs_full}"
        )

    context_block = "\n\n====\n\n".join(context_blocks) if context_blocks else ""

    # Build the final user prompt (either via template or fallback).
    if template:
        user_payload = (
            template.replace("__NOW__", now)
            .replace("__USER_MESSAGE__", user_message)
            .replace("__MEMORIES_BLOCK__", memories_block)
            .replace("__RECENT_CONVERSATION_BLOCK__", recent_conversation_block)
            .replace("__OPEN_DOCUMENTS_INDEX__", open_docs_index)
            .replace("__OPEN_DOCUMENTS_FULL__", open_docs_full)
            .replace("__CONTEXT_BLOCK__", context_block)
        )
    else:
        # Fallback should never be hit now that the template file exists.
        # This prevents the entire massive inline prompt from living in code.
        user_payload = (
            f"Current time: {now}\n\n"
            f"User message:\n{user_message}\n\n"
            "Note: answer prompt template not found; documents, memories, and chat "
            "history are omitted."
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
) -> str:
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

    if reflection_history_limit <= 0:
        recent_conversation_block = ""
    else:
        recent_conversation_block = thalamus.history.formatted_block(
            limit=reflection_history_limit
        )

    # Prefer an external template if available; fall back to the
    # existing inline prompt if not.
    template = thalamus._load_prompt_template("reflection")
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
            "Reflection prompt template missing; no reflection will be stored.\n\n"
            f"Current time: {now}\n\n"
            f"User message:\n{user_message}\n\n"
            f"Assistant message:\n{assistant_message}\n\n"
            "Recent conversation (may be empty):\n"
            f"{recent_conversation_block}"
        )

    thalamus._debug_log(
        session_id,
        "llm_reflection_prompt",
        f"User payload for reflection:\n{user_prompt}",
    )

    messages = [
        {"role": "user", "content": user_prompt},
    ]
    return thalamus.ollama.chat(messages)
