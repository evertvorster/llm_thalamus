from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from llm_thalamus.config.access import get_config
from llm_thalamus.core.prompting.fill_tokens import fill_template
from llm_thalamus.core.prompting.prompt_texts import load_prompt_text


@dataclass(frozen=True)
class AnswerPromptInputs:
    now_iso: str
    user_message: str
    recent_conversation_block: str
    memories_block: str
    history_message_limit: int
    memory_limit: int


def _default_block(s: str, fallback: str) -> str:
    s = (s or "").strip()
    return s if s else fallback


def assemble_answer_prompt(inputs: AnswerPromptInputs) -> str:
    """
    Pure prompt assembly. No I/O, no OpenMemory access, no history access.
    """
    cfg = get_config()
    template = load_prompt_text("answer")

    memories_block = _default_block(inputs.memories_block, "(no relevant memories found.)")
    recent_block = _default_block(inputs.recent_conversation_block, "(no recent chat history available.)")

    tokens: Mapping[str, str] = {
        "NOW": inputs.now_iso,
        "USER_MESSAGE": inputs.user_message,
        "CHAT_HISTORY_BLOCK": recent_block,
        "MEMORIES_BLOCK": memories_block,
        "HISTORY_MESSAGE_LIMIT": str(inputs.history_message_limit),
        "MEMORY_LIMIT": str(inputs.memory_limit),
        # if your template still uses model id anywhere:
        "MODEL_NAME": getattr(cfg, "llm_model", ""),
    }

    return fill_template(template, tokens)
