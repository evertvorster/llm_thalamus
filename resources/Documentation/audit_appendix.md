# LLM Thalamus – Audit Appendix

Snapshot: provided snapshot (zip sha1 692b18d7223b5a1fe1a8d463f01aaa3d65126ee6) | Date: 2026-03-05

## A1) Prompt token inventory
Prompt templates and detected `<<TOKEN>>` placeholders:

| Prompt path | Tokens |
|---|---|
| `resources/prompts/runtime_answer.txt` | `<<CONTEXT_JSON>>`, `<<ISSUES_JSON>>`, `<<NOW_ISO>>`, `<<STATUS>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_context_builder.txt` | `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<ROLE_KEY>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_memory_retriever.txt` | `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<NOW_ISO>>`, `<<REQUESTED_LIMIT>>`, `<<ROLE_KEY>>`, `<<TIMEZONE>>`, `<<TOPICS_JSON>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_memory_writer.txt` | `<<ASSISTANT_ANSWER>>`, `<<CONTEXT_JSON>>`, `<<NODE_ID>>`, `<<NOW_ISO>>`, `<<ROLE_KEY>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_reflect_topics.txt` | `<<ASSISTANT_ANSWER>>`, `<<TOPICS_JSON>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_router.txt` | `<<CONTEXT_JSON>>`, `<<NOW_ISO>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |
| `resources/prompts/runtime_world_modifier.txt` | `<<USER_MESSAGE>>`, `<<WORLD_JSON>>` |

Notable: `resources/prompts/runtime_memory_retriever.txt` includes `<<REQUESTED_LIMIT>>`, which must be supplied by token rendering or it will surface as an unresolved token error.

## A2) Tool skill catalog
| Skill | Tools |
|---|---|
| `core_context` | `chat_history_tail` |
| `core_world` | `world_apply_ops` |
| `mcp_memory_read` | `memory_query` |
| `mcp_memory_write` | `memory_store` |

## A3) Node → skill allowlist policy
| Node key | Allowed skills | Resulting tool names |
|---|---|---|
| `router` | `core_context`, `mcp_memory_read` | `chat_history_tail`, `memory_query` |
| `context_builder` | `core_context`, `mcp_memory_read` | `chat_history_tail`, `memory_query` |
| `memory_retriever` | `mcp_memory_read` | `memory_query` |
| `world_modifier` | `core_world` | `world_apply_ops` |
| `memory_writer` | `mcp_memory_write` | `memory_store` |

## A4) Node registration constants (from node modules)
| Module | NODE_ID | PROMPT_NAME |
|---|---|---|
| `src/runtime/nodes/llm_answer.py` | `llm.answer` | `runtime_answer` |
| `src/runtime/nodes/llm_context_builder.py` | `llm.context_builder` | `runtime_context_builder` |
| `src/runtime/nodes/llm_memory_retriever.py` | `llm.memory_retriever` | `runtime_memory_retriever` |
| `src/runtime/nodes/llm_memory_writer.py` | `llm.memory_writer` | `runtime_memory_writer` |
| `src/runtime/nodes/llm_reflect_topics.py` | `llm.reflect_topics` | `runtime_reflect_topics` |
| `src/runtime/nodes/llm_router.py` | `llm.router` | `runtime_router` |
| `src/runtime/nodes/llm_world_modifier.py` | `llm.world_modifier` | `runtime_world_modifier` |
