# LLM Thalamus – Audit Appendix

## A) Prompt Token Inventory
- `resources/prompts/runtime_router.txt`: `<<CONTEXT_JSON>>`, `<<NOW_ISO>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_context_builder.txt`: `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<ROLE_KEY>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_memory_retriever.txt`: `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<NOW_ISO>>`, `<<REQUESTED_LIMIT>>`, `<<ROLE_KEY>>`, `<<TIMEZONE>>`, `<<TOPICS_JSON>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_world_modifier.txt`: `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_answer.txt`: `<<CONTEXT_JSON>>`, `<<ISSUES_JSON>>`, `<<NOW_ISO>>`, `<<STATUS>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_reflect_topics.txt`: `<<ASSISTANT_ANSWER>>`, `<<TOPICS_JSON>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- `resources/prompts/runtime_memory_writer.txt`: `<<ASSISTANT_ANSWER>>`, `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<NOW_ISO>>`, `<<ROLE_KEY>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`

## B) Files that look stale, duplicated, or legacy
- `F042` `src/runtime/build.py`: older minimal graph builder
- `F048` `src/runtime/graph_policy.py`: `_next_node` path not used by current graph
- `F052` `src/runtime/prompt_loader.py`: superseded by `Deps.load_prompt()`
- `F049` `src/runtime/json_extract.py`: duplicate JSON extraction helper
- `F090` `src/runtime/providers/validate.py`: older validation path
- `F092` `src/runtime/tools/registry.py`: demo echo toolset not used by RuntimeToolkit

## C) Documentation/code mismatches
- `README.md` and `README_developer.md` claim local SQLite memory/episode stores. No such implementation exists in `src/`.
- `README_developer.md` refers to `graph_nodes.py`; current registry file is `src/runtime/registry.py`.
- `CONTRIBUTING.md` references old run paths and setup flow.
- The user prompt listed `.continue/` and `.vscode/`, but those directories are absent from the provided zip.

## D) Current node -> skill policy
- router -> `core_context`, `mcp_memory_read`
- context_builder -> `core_context`, `mcp_memory_read`
- memory_retriever -> `mcp_memory_read`
- world_modifier -> `core_world`
- memory_writer -> `mcp_memory_write`

Source: `F109`.

## E) Durable world schema observed in code
```json
{
  "updated_at": "<iso timestamp>",
  "project": "",
  "topics": [],
  "goals": [],
  "rules": [],
  "identity": {
    "user_name": "",
    "session_user_name": "",
    "agent_name": "",
    "user_location": ""
  },
  "tz": "<optional>"
}
```

## F) Unknown from snapshot
- Any `.continue` agent/MCP/rule files
- Any `.vscode` workspace settings
- Any real CI workflow files
- Any commit hash for the repo state
- Any local SQLite schema or migration files for episodes/memory databases
