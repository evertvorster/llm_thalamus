from __future__ import annotations

from llm_thalamus.adapters.openmemory.client import assert_db_present
from llm_thalamus.config.access import get_config
from llm_thalamus.core.state.conversation_history import ConversationHistory
from llm_thalamus.core.memory.memory_gateway import retrieve_relevant_memories_text
from llm_thalamus.core.memory.reflection_writes import (
    store_reflection_writes,
    delete_written_memories,
)


def main() -> None:
    # Probe policy: validate real runtime state for stateful modules.
    assert_db_present()

    cfg = get_config()

    # --- short-term buffer (pure logic) ---
    max_msgs = int(getattr(cfg, "short_term_max_messages", 7))
    hist = ConversationHistory(max_msgs)
    hist.add("human", "hello")
    hist.add("assistant", "hi")
    hist.add("human", "what's up?")
    formatted = hist.formatted_block(limit=3)

    # --- memory read (compat path) ---
    # We don't assert non-empty; empty is legitimate.
    mem_text = retrieve_relevant_memories_text("test", k=1)

    # --- reflection write (RW) ---
    # Throwaway memory write is OK; probe cleans up if ids are available.
    reflection = (
        "```json\n"
        "{\"memory_writes\":["
        "{\"content\":\"PROBE: throwaway memory write\",\"tag\":\"probe\",\"metadata\":{\"content_type\":\"text\"}}"
        "]}\n"
        "```\n"
    )

    ids = store_reflection_writes(reflection, session_id="probe-session")

    if ids:
        delete_written_memories(ids)

    print("probe_context_components: OK")
    print(f"  short_term_max_messages={max_msgs}")
    print(f"  formatted_head={formatted[:80]}")
    print(f"  memories_chars={len(mem_text)}")
    print(f"  wrote_ids={len(ids)}")


if __name__ == "__main__":
    main()

