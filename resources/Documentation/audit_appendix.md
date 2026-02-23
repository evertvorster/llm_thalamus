# Audit Appendix
- Snapshot sha256: `aca4ad64a29b8260f512d101af1bdc7b9d5424458f6e287e9420ec234acc9c14`
- Generated: 2026-02-23

## A1) Prompt templates and tokens
- `resources/prompts/runtime_answer.txt` (37 lines): tokens = CONTEXT_JSON, ISSUES_JSON, NOW_ISO, STATUS, TIMEZONE, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_context_builder.txt` (65 lines): tokens = EXISTING_CONTEXT_JSON, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_memory_retriever.txt` (66 lines): tokens = CONTEXT_JSON, NODE_ID, NOW_ISO, REQUESTED_LIMIT, ROLE_KEY, TIMEZONE, TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_memory_writer.txt` (52 lines): tokens = ASSISTANT_ANSWER, CONTEXT_JSON, NODE_ID, NOW_ISO, ROLE_KEY, TIMEZONE, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_reflect_topics.txt` (37 lines): tokens = ASSISTANT_MESSAGE, PREV_TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_router.txt` (41 lines): tokens = NOW, TZ, USER_MESSAGE, WORLD_JSON
- `resources/prompts/runtime_world_modifier.txt` (53 lines): tokens = USER_MESSAGE, WORLD_JSON

## A2) Tool catalog (by definition)
- `chat_history_tail`: schema in `src/runtime/tools/definitions/chat_history_tail.py`; handler in `src/runtime/tools/bindings/chat_history_tail.py`
- `world_apply_ops`: schema in `src/runtime/tools/definitions/world_apply_ops.py`; handler in `src/runtime/tools/bindings/world_apply_ops.py`
- `memory_query`: schema in `src/runtime/tools/definitions/memory_query.py`; handler in `src/runtime/tools/bindings/memory_query.py`
- `memory_store`: schema in `src/runtime/tools/definitions/memory_store.py`; handler in `src/runtime/tools/bindings/memory_store.py`

## A3) Node→skill allowlist (code-level)
```python
NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # Context builder can assemble context from core sources and MCP memory reads.
    "context_builder": {"core_context", "mcp_memory_read"},

    # Memory retriever reads memories only.
    "memory_retriever": {"mcp_memory_read"},

    # World modifier gets only world ops.
    "world_modifier": {"core_world"},

    # Memory writer writes memories only.
    "memory_writer": {"mcp_memory_write"},
```

## A4) Files present in snapshot but likely local artifacts
- `thinking-manual-1771777675.log` (F219)
- `thinking-manual-1771780170.log` (F220)
- `var/llm-thalamus-dev/data/chat_history.jsonl` (F221)
- `var/llm-thalamus-dev/data/episodes.sqlite` (F222)
- `var/llm-thalamus-dev/data/memory.sqlite` (F223)
- `var/llm-thalamus-dev/state/world_state.json` (F224)

## A5) Packaging mismatches observed
- `Makefile` references `llm_thalamus/llm_thalamus_ui.py` and `llm_thalamus/llm_thalamus.py`, but the snapshot code lives under `src/` and no such paths exist.
- `llm_thalamus.desktop` launches `llm-thalamus-ui`, but no such executable/script is present in the snapshot.
