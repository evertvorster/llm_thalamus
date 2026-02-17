from __future__ import annotations

import os
from pathlib import Path


def run() -> None:
    # 1) Force OpenMemory adapter initialization FIRST (sets env + delayed import)
    from llm_thalamus.adapters.openmemory import client as om_client
    from llm_thalamus.config.access import get_config

    cfg = get_config()

    print("probe_context_components: DIAGNOSTICS")
    try:
        db_path = cfg.openmemory_db_path() if callable(cfg.openmemory_db_path) else cfg.openmemory_db_path
    except Exception:
        db_path = None

    try:
        db_url = cfg.openmemory_db_url() if callable(cfg.openmemory_db_url) else cfg.openmemory_db_url
    except Exception:
        db_url = None

    print(f"  cfg.openmemory_db_path={db_path}")
    print(f"  cfg.openmemory_db_url={db_url}")

    cwd_db = Path("openmemory.db")
    print(f"  cwd_openmemory_db_preexists={cwd_db.exists()}  path={cwd_db.resolve()}")

    # This should set OM_* env vars and instantiate Memory correctly.
    om_client.get_memory()

    env_keys = [
        "OM_DB_URL",
        "OM_TIER",
        "OM_EMBEDDINGS_PROVIDER",
        "OM_OLLAMA_URL",
        "OM_OLLAMA_EMBEDDING_MODEL",
        "OM_OLLAMA_EMBEDDINGS_MODEL",
        "OLLAMA_URL",
    ]
    print("  env_after_adapter_init:")
    for k in env_keys:
        print(f"    {k}={os.environ.get(k)}")

    print(f"  cwd_openmemory_db_after_init={cwd_db.exists()}")

    # 2) Only now import the context components and run the actual test
    #    (If any module bypasses the adapter, it will now be obvious from env above.)
    from llm_thalamus.core.state.conversation_history import ConversationHistory
    from llm_thalamus.core.memory import select_memories  # compatibility module(s)

    # Minimal “real-ish” data: 2 user turns + 1 assistant turn
    hist = ConversationHistory(short_term_max_messages=7)
    hist.add_user_message("hello")
    hist.add_assistant_message("hi")
    hist.add_user_message("what's up?")

    formatted = hist.format_for_prompt()
    print("probe_context_components: HISTORY")
    print(f"  short_term_max_messages={hist.short_term_max_messages}")
    print(f"  formatted_head={formatted[:80].replace(chr(10),' ')}")

    # If context calls memory selection, do it through the compatibility path
    # (This is where your 1536/768 mismatch is currently triggered.)
    # Keep k tiny.
    memories_text = select_memories.select_memories_text(
        query="test",
        k=1,
        user_id=om_client.get_default_user_id(),
        cfg=cfg,
    )
    print("probe_context_components: MEMORIES")
    print(f"  memories_chars={len(memories_text or '')}")

    print("probe_context_components: OK")


if __name__ == "__main__":
    run()
