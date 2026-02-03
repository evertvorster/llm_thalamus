from __future__ import annotations

from datetime import datetime

from llm_thalamus.config.access import get_config
from llm_thalamus.core.prompting.assemble_answer import AnswerPromptInputs, assemble_answer_prompt
from llm_thalamus.core.state.message_history import MessageHistoryStore


def _read_memories_block_via_gateway(cfg, user_message: str) -> str:
    """
    Must NOT touch OpenMemory directly.

    This probe must go through core/memory/memory_gateway.py (whatever API it exposes),
    which in turn is responsible for using adapters/openmemory/client.py as the only
    OpenMemory access path.
    """
    import llm_thalamus.core.memory.memory_gateway as mg

    # Class-based gateways (try common names)
    for cls_name in ("MemoryGateway", "MemoryReadGateway", "MemoriesGateway", "MemoryGatewayReader"):
        cls = getattr(mg, cls_name, None)
        if cls is None:
            continue

        # Prefer a from_config constructor if present
        if hasattr(cls, "from_config"):
            obj = cls.from_config(cfg)  # type: ignore[attr-defined]
        else:
            obj = cls(cfg)  # type: ignore[call-arg]

        # Prefer common method names
        for meth in ("read_memories_block", "get_memories_block", "memories_block", "read_block", "get_block"):
            fn = getattr(obj, meth, None)
            if callable(fn):
                return fn(user_message=user_message)

        raise RuntimeError(
            f"{cls_name} exists but has no known block method. "
            f"Available attrs: {sorted(a for a in dir(obj) if not a.startswith('_'))}"
        )

    # Function-based gateways (try common names)
    for fn_name in ("read_memories_block", "get_memories_block", "memories_block", "read_block", "get_block"):
        fn = getattr(mg, fn_name, None)
        if callable(fn):
            # Support either (cfg, user_message) or keyword forms
            try:
                return fn(cfg=cfg, user_message=user_message)
            except TypeError:
                try:
                    return fn(cfg, user_message)
                except TypeError:
                    return fn(user_message=user_message)

    raise RuntimeError(
        "memory_gateway module has no recognized public API for reading memories block. "
        f"Exports: {sorted(a for a in dir(mg) if not a.startswith('_'))}"
    )


def main() -> int:
    cfg = get_config()

    # Real persisted history (no fakery)
    history = MessageHistoryStore.from_config(cfg)
    recent_block = history.formatted_head(limit=cfg.thalamus.short_term_max_messages)

    user_message = "Probe: assemble answer prompt from real history + real memory store."

    # Real memory retrieval via gateway (which must use adapters/openmemory/client.py internally)
    memories_block = _read_memories_block_via_gateway(cfg, user_message=user_message)

    inputs = AnswerPromptInputs(
        now_iso=datetime.now().isoformat(timespec="seconds"),
        user_message=user_message,
        recent_conversation_block=recent_block,
        memories_block=memories_block,
        history_message_limit=cfg.thalamus.short_term_max_messages,
        memory_limit=cfg.thalamus.memory_limit,
    )

    prompt = assemble_answer_prompt(inputs)

    print("probe_prompt_assemble_answer: OK")
    print(f"  prompt_len_chars={len(prompt)}")
    print(f"  approx_tokens={len(prompt)//4}")
    print(f"  head={prompt[:400].replace(chr(10), '\\\\n')}")
    return 0
