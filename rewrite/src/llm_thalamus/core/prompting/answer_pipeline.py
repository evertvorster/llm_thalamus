from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from llm_thalamus.config.access import get_config
from llm_thalamus.core.prompting.assemble_answer import AnswerPromptInputs, assemble_answer_prompt
from llm_thalamus.core.state.message_history import MessageHistoryStore


def _cfg_int(cfg: object, names: tuple[str, ...], default: int) -> int:
    for name in names:
        if hasattr(cfg, name):
            try:
                return int(getattr(cfg, name))
            except Exception:
                pass
    return default


def _recent_history_block(history: object, limit: int) -> str:
    fmt = getattr(history, "format_for_prompt", None)
    if callable(fmt):
        try:
            return fmt(limit=limit)
        except TypeError:
            return fmt(limit)
    raise RuntimeError(
        "MessageHistoryStore missing required formatter method format_for_prompt. "
        f"Available attrs: {sorted(a for a in dir(history) if not a.startswith('_'))}"
    )


def _format_memories_block(results: List[Dict[str, Any]], max_items: int) -> str:
    if not results:
        return "(no relevant memories found.)"

    lines: List[str] = []
    for i, r in enumerate(results[:max_items], start=1):
        content = str(r.get("content", "") or "").strip()
        if not content:
            continue
        sector = str(r.get("primary_sector", "") or "").strip()
        score = r.get("score", None)

        header = f"{i}."
        if sector:
            header += f" [{sector}]"
        if score is not None:
            header += f" score={score}"

        if len(content) > 800:
            content = content[:799] + "…"

        lines.append(f"{header}\n{content}")

    return "\n\n".join(lines).strip() if lines else "(no relevant memories found.)"


@dataclass(frozen=True)
class AnswerPipelineConfig:
    short_term_max: int = 7
    memory_limit: int = 8
    user_id: str = "default"
    
def _now_iso() -> str:
    # Stable, readable UTC timestamp for prompts
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _make_answer_prompt_inputs(
    *,
    user_message: str,
    recent_block: str,
    memories_block: str,
    history_message_limit: int,
    memory_limit: int,
) -> AnswerPromptInputs:
    """Construct AnswerPromptInputs using the current assemble_answer signature."""
    sig = inspect.signature(AnswerPromptInputs)
    params = list(sig.parameters.keys())
    if params and params[0] == "self":
        params = params[1:]

    kw = {}

    # Required fields (based on your current signature)
    if "now_iso" in params:
        kw["now_iso"] = _now_iso()
    if "user_message" in params:
        kw["user_message"] = user_message
    else:
        raise TypeError(f"AnswerPromptInputs missing 'user_message'. Params: {params}")

    if "recent_conversation_block" in params:
        kw["recent_conversation_block"] = recent_block
    else:
        raise TypeError(f"AnswerPromptInputs missing 'recent_conversation_block'. Params: {params}")

    if "memories_block" in params:
        kw["memories_block"] = memories_block
    else:
        raise TypeError(f"AnswerPromptInputs missing 'memories_block'. Params: {params}")

    if "history_message_limit" in params:
        kw["history_message_limit"] = int(history_message_limit)
    if "memory_limit" in params:
        kw["memory_limit"] = int(memory_limit)

    return AnswerPromptInputs(**kw)


def build_answer_prompt(user_message: str, *, cfg: Optional[object] = None) -> str:
    """Pure-ish builder: assembles the answer prompt from runtime sources.

    - loads config if not provided
    - reads recent history from MessageHistoryStore
    - retrieves memories via adapters.openmemory.client (ONLY)
    - assembles final prompt via core.prompting.assemble_answer
    """
    if cfg is None:
        cfg = get_config()

    pipe_cfg = AnswerPipelineConfig(
        short_term_max=_cfg_int(cfg, ("short_term_max", "history_max", "short_term_history_max"), 7),
        memory_limit=_cfg_int(cfg, ("memory_limit", "memory_k", "k_memories"), 8),
        user_id=getattr(cfg, "default_user_id", "default") or "default",
    )

    history = MessageHistoryStore.from_config()
    recent_block = _recent_history_block(history, limit=pipe_cfg.short_term_max)

    # OpenMemory access must go ONLY through this adapter.
    from llm_thalamus.adapters.openmemory import client as om_client

    # Ensure env is configured in-process; adapter enforces this.
    om_client.get_memory()
    results = om_client.search(query=user_message, k=pipe_cfg.memory_limit, user_id=pipe_cfg.user_id)
    memories_block = _format_memories_block(results, max_items=pipe_cfg.memory_limit)

    inputs = _make_answer_prompt_inputs(
        user_message=user_message,
        recent_block=recent_block,
        memories_block=memories_block,
    )
    return assemble_answer_prompt(inputs)


def answer_via_ollama(user_message: str, *, cfg: Optional[object] = None, timeout: int = 120) -> str:
    """End-to-end: build prompt and call the configured Ollama model."""
    if cfg is None:
        cfg = get_config()

    prompt = build_answer_prompt(user_message, cfg=cfg)

    from llm_thalamus.adapters.llm.ollama import OllamaClient

    base_url = getattr(cfg, "ollama_url", None) or "http://localhost:11434"
    model = getattr(cfg, "llm_model", None) or "qwen2.5:14b"

    client = OllamaClient(base_url=base_url, model=model)
    return client.chat(messages=[{"role": "user", "content": prompt}], timeout=timeout)
