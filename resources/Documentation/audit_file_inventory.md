# 10) Per-File Inventory (complete)
This document enumerates **every file present in the provided snapshot**.
Legend:
- **ID**: stable reference (F###)
- **Inbound deps** / **Outbound deps**: only computed for Python modules under `src/`
- **Key symbols**: top-level `class`/`def`/ALL_CAPS constants for Python; token list for prompt templates

## (root)/
### F001: `CONTRIBUTING.md`
- **Purpose:** Markdown documentation.
- **Size:** 2941 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F002: `LICENSE.md`
- **Purpose:** Markdown documentation.
- **Size:** 35149 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F003: `Makefile`
- **Purpose:** Packaging/desktop integration artifact.
- **Size:** 2328 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** may be stale vs src/ layout (Makefile references non-existent llm_thalamus/ package)
### F004: `README.md`
- **Purpose:** Markdown documentation.
- **Size:** 5234 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F005: `llm_thalamus.desktop`
- **Purpose:** Packaging/desktop integration artifact.
- **Size:** 246 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** may be stale vs src/ layout (Makefile references non-existent llm_thalamus/ package)
### F219: `thinking-manual-1771777675.log`
- **Purpose:** Log artifact (likely local run output).
- **Size:** 38464 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F220: `thinking-manual-1771780170.log`
- **Purpose:** Log artifact (likely local run output).
- **Size:** 30292 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —

## resources/
### F006: `resources/Documentation/Node_template.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6375 bytes
- **Key symbols:** functions: _get_emitter, _parse_first_json_object, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F007: `resources/Documentation/Prompt_template.txt`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1604 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F008: `resources/config/config.json`
- **Purpose:** Config template or resources-level configuration.
- **Size:** 3748 bytes
- **Key symbols:** (config template JSON)
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F009: `resources/graphics/inactive.jpg`
- **Purpose:** UI image/graphic asset.
- **Size:** 117173 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only)
### F010: `resources/graphics/llm.jpg`
- **Purpose:** UI image/graphic asset.
- **Size:** 114908 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only)
### F011: `resources/graphics/llm_thalamus.svg`
- **Purpose:** UI image/graphic asset.
- **Size:** 1089815 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F012: `resources/graphics/thalamus.jpg`
- **Purpose:** UI image/graphic asset.
- **Size:** 99414 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only)
### F013: `resources/prompts/runtime_answer.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 803 bytes
- **Key symbols:** tokens: CONTEXT_JSON, ISSUES_JSON, NOW_ISO, STATUS, TIMEZONE, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F014: `resources/prompts/runtime_context_builder.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 2066 bytes
- **Key symbols:** tokens: EXISTING_CONTEXT_JSON, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F015: `resources/prompts/runtime_memory_retriever.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 1326 bytes
- **Key symbols:** tokens: CONTEXT_JSON, NODE_ID, NOW_ISO, REQUESTED_LIMIT, ROLE_KEY, TIMEZONE, TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F016: `resources/prompts/runtime_memory_writer.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 1646 bytes
- **Key symbols:** tokens: ASSISTANT_ANSWER, CONTEXT_JSON, NODE_ID, NOW_ISO, ROLE_KEY, TIMEZONE, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F017: `resources/prompts/runtime_reflect_topics.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 1406 bytes
- **Key symbols:** tokens: ASSISTANT_MESSAGE, PREV_TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F018: `resources/prompts/runtime_router.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 1097 bytes
- **Key symbols:** tokens: NOW, TZ, USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F019: `resources/prompts/runtime_world_modifier.txt`
- **Purpose:** Prompt template used by one runtime node (tokens rendered by runtime.prompting.render_tokens).
- **Size:** 1761 bytes
- **Key symbols:** tokens: USER_MESSAGE, WORLD_JSON
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —

## src/
### F020: `src/__pycache__/llm_thalamus.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3610 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F021: `src/config/__init__.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3278 bytes
- **Key symbols:** classes: ConfigSnapshot; functions: bootstrap_config
- **Inbound deps:** llm_thalamus
- **Outbound deps:** —
- **Notes/risks:** —
### F022: `src/config/__pycache__/__init__.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3992 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F023: `src/config/__pycache__/__init__.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4315 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F024: `src/config/__pycache__/_cli.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1791 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F025: `src/config/__pycache__/_cli.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1924 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F026: `src/config/__pycache__/_load.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2851 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F027: `src/config/__pycache__/_load.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2806 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F028: `src/config/__pycache__/_policy.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 5812 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F029: `src/config/__pycache__/_policy.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6179 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F030: `src/config/__pycache__/_rootfind.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 937 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F031: `src/config/__pycache__/_rootfind.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1024 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F032: `src/config/__pycache__/_schema.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8529 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F033: `src/config/__pycache__/_schema.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 9900 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F034: `src/config/_cli.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 687 bytes
- **Key symbols:** classes: BootstrapArgs; functions: _env_truthy, parse_bootstrap_args
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F035: `src/config/_load.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1293 bytes
- **Key symbols:** functions: ensure_config_file_exists, load_raw_config_json
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F036: `src/config/_policy.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4007 bytes
- **Key symbols:** classes: Roots; functions: compute_roots_for_mode, format_mode_summary, resolve_resource_path, resolve_writable_path
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F037: `src/config/_rootfind.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 451 bytes
- **Key symbols:** functions: find_project_root
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F038: `src/config/_schema.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8187 bytes
- **Key symbols:** classes: EffectiveValues; functions: _get_dict, _get_float, _get_int, _get_str, extract_effective_values
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F039: `src/controller/__pycache__/chat_history.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6268 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F040: `src/controller/__pycache__/chat_history.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6567 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F041: `src/controller/__pycache__/chat_history_service.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1321 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F042: `src/controller/__pycache__/runtime_services.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1973 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F043: `src/controller/__pycache__/worker.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 14696 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F044: `src/controller/__pycache__/worker.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 16738 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F045: `src/controller/__pycache__/world_state.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3046 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F046: `src/controller/__pycache__/world_state.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3232 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F047: `src/controller/chat_history.py`
- **Purpose:** Append/read JSONL chat history and provide tail functionality.
- **Size:** 2662 bytes
- **Key symbols:** classes: ChatTurn; functions: _parse_line, append_turn, ensure_history_file, format_for_prompt, now_iso_utc, read_tail, trim_to_max
- **Inbound deps:** controller.chat_history_service, controller.worker
- **Outbound deps:** —
- **Notes/risks:** —
### F048: `src/controller/chat_history_service.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 488 bytes
- **Key symbols:** classes: FileChatHistoryService
- **Inbound deps:** controller.runtime_services
- **Outbound deps:** controller.chat_history
- **Notes/risks:** —
### F049: `src/controller/mcp/__pycache__/client.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 11582 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F050: `src/controller/mcp/__pycache__/transport_streamable_http.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3245 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F051: `src/controller/mcp/client.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8143 bytes
- **Key symbols:** classes: MCPClient, MCPServerConfig, MCPToolCallResult
- **Inbound deps:** controller.runtime_services
- **Outbound deps:** controller.mcp.transport_streamable_http
- **Notes/risks:** —
### F052: `src/controller/mcp/transport_streamable_http.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1539 bytes
- **Key symbols:** classes: HttpResponse, StreamableHttpTransport
- **Inbound deps:** controller.mcp.client
- **Outbound deps:** —
- **Notes/risks:** —
### F053: `src/controller/runtime_services.py`
- **Purpose:** Builds RuntimeServices (tool resources + toolkit) and wires MCP OpenMemory client.
- **Size:** 1611 bytes
- **Key symbols:** functions: build_runtime_services
- **Inbound deps:** controller.worker
- **Outbound deps:** controller.chat_history_service, controller.mcp.client, runtime.services, runtime.tools.resources, runtime.tools.toolkit
- **Notes/risks:** —
### F054: `src/controller/worker.py`
- **Purpose:** Central Qt worker orchestrating a turn: persistence writes, LangGraph execution, TurnEvent→Qt signal bridging.
- **Size:** 11625 bytes
- **Key symbols:** classes: ControllerWorker; functions: _now_iso_local
- **Inbound deps:** —
- **Outbound deps:** controller.chat_history, controller.runtime_services, controller.world_state, runtime.deps, runtime.langgraph_runner, runtime.state
- **Notes/risks:** —
### F055: `src/controller/world_state.py`
- **Purpose:** Load/commit durable world_state.json with defaults and corruption recovery.
- **Size:** 1892 bytes
- **Key symbols:** functions: commit_world_state, default_world, load_world_state
- **Inbound deps:** controller.worker, runtime.tools.bindings.world_apply_ops
- **Outbound deps:** —
- **Notes/risks:** —
### F056: `src/llm_thalamus.py`
- **Purpose:** Qt application entrypoint; boots config, controller worker, and main window.
- **Size:** 1763 bytes
- **Key symbols:** functions: main
- **Inbound deps:** —
- **Outbound deps:** config
- **Notes/risks:** —
### F057: `src/runtime/__init__.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 128 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F058: `src/runtime/__pycache__/__init__.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 308 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F059: `src/runtime/__pycache__/__init__.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 294 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F060: `src/runtime/__pycache__/build.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1844 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F061: `src/runtime/__pycache__/build.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1823 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F062: `src/runtime/__pycache__/deps.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 12699 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F063: `src/runtime/__pycache__/deps.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 13128 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F064: `src/runtime/__pycache__/emitter.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 7676 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F065: `src/runtime/__pycache__/emitter.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8907 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F066: `src/runtime/__pycache__/event_bus.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4328 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F067: `src/runtime/__pycache__/event_bus.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4776 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F068: `src/runtime/__pycache__/events.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 10679 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F069: `src/runtime/__pycache__/events.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 13041 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F070: `src/runtime/__pycache__/graph_build.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1705 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F071: `src/runtime/__pycache__/graph_build.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3063 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F072: `src/runtime/__pycache__/graph_nodes.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1947 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F073: `src/runtime/__pycache__/graph_nodes.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2476 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F074: `src/runtime/__pycache__/graph_policy.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 611 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F075: `src/runtime/__pycache__/graph_policy.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 701 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F076: `src/runtime/__pycache__/json_extract.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1985 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F077: `src/runtime/__pycache__/json_extract.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2006 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F078: `src/runtime/__pycache__/langgraph_runner.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6478 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F079: `src/runtime/__pycache__/langgraph_runner.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 6251 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F080: `src/runtime/__pycache__/prompt_loader.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 635 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F081: `src/runtime/__pycache__/prompting.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1102 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F082: `src/runtime/__pycache__/prompting.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1129 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F083: `src/runtime/__pycache__/registry.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1906 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F084: `src/runtime/__pycache__/registry.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2117 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F085: `src/runtime/__pycache__/run.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1185 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F086: `src/runtime/__pycache__/services.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1025 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F087: `src/runtime/__pycache__/state.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1882 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F088: `src/runtime/__pycache__/state.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2224 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F089: `src/runtime/__pycache__/tool_loop.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 5470 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F090: `src/runtime/__pycache__/tool_loop.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8164 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F091: `src/runtime/build.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 866 bytes
- **Key symbols:** functions: build_compiled_graph, run_graph
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.nodes, runtime.registry, runtime.state
- **Notes/risks:** —
### F092: `src/runtime/deps.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8028 bytes
- **Key symbols:** classes: Deps, RoleLLM, RoleSpec; functions: _chat_params_from_mapping, _get_cfg_value, _maybe_float, _maybe_int, _maybe_str_list, _normalize_response_format, _validate_required_models_or_die, build_runtime_deps
- **Inbound deps:** controller.worker, runtime.build, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry, runtime.tool_loop
- **Outbound deps:** runtime.providers.base, runtime.providers.factory, runtime.providers.types
- **Notes/risks:** —
### F093: `src/runtime/emitter.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4214 bytes
- **Key symbols:** classes: NodeSpan, TurnEmitter
- **Inbound deps:** runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.tool_loop
- **Outbound deps:** runtime.events
- **Notes/risks:** —
### F094: `src/runtime/event_bus.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3006 bytes
- **Key symbols:** classes: EventBus
- **Inbound deps:** runtime.langgraph_runner
- **Outbound deps:** runtime.events
- **Notes/risks:** —
### F095: `src/runtime/events.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 8282 bytes
- **Key symbols:** classes: TurnEvent, TurnEventFactory; functions: assert_turn_event, is_turn_event; constants: EVENT_PROTOCOL_VERSION
- **Inbound deps:** runtime.emitter, runtime.event_bus, runtime.langgraph_runner
- **Outbound deps:** —
- **Notes/risks:** —
### F096: `src/runtime/graph_build.py`
- **Purpose:** Defines LangGraph StateGraph topology and branches based on router output.
- **Size:** 2119 bytes
- **Key symbols:** functions: build_compiled_graph
- **Inbound deps:** runtime.langgraph_runner
- **Outbound deps:** runtime.nodes, runtime.registry, runtime.state
- **Notes/risks:** —
### F097: `src/runtime/graph_nodes.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1062 bytes
- **Key symbols:** functions: collect_streamed_response, emit_final, emit_log, emit_node_end, emit_node_start
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F098: `src/runtime/graph_policy.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 237 bytes
- **Key symbols:** functions: route_after_router
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F099: `src/runtime/json_extract.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1449 bytes
- **Key symbols:** functions: extract_first_json_object
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F100: `src/runtime/langgraph_runner.py`
- **Purpose:** Runs a single LangGraph turn in a background thread and streams TurnEvents via EventBus.
- **Size:** 3581 bytes
- **Key symbols:** functions: _provider_name, run_turn_runtime
- **Inbound deps:** controller.worker
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.event_bus, runtime.events, runtime.graph_build, runtime.services, runtime.state
- **Notes/risks:** —
### F101: `src/runtime/nodes/__init__.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 350 bytes
- **Key symbols:** —
- **Inbound deps:** runtime.build, runtime.graph_build
- **Outbound deps:** —
- **Notes/risks:** —
### F102: `src/runtime/nodes/__pycache__/__init__.cpython-311.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 388 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F103: `src/runtime/nodes/__pycache__/__init__.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 502 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F104: `src/runtime/nodes/__pycache__/llm_answer.cpython-311.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 5376 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F105: `src/runtime/nodes/__pycache__/llm_answer.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 6761 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F106: `src/runtime/nodes/__pycache__/llm_context_builder.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 13119 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F107: `src/runtime/nodes/__pycache__/llm_memory_retriever.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 11269 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F108: `src/runtime/nodes/__pycache__/llm_memory_writer.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 10279 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F109: `src/runtime/nodes/__pycache__/llm_reflect_topics.cpython-311.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 6372 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F110: `src/runtime/nodes/__pycache__/llm_reflect_topics.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 6962 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F111: `src/runtime/nodes/__pycache__/llm_router.cpython-311.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 5322 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F112: `src/runtime/nodes/__pycache__/llm_router.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 6421 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F113: `src/runtime/nodes/__pycache__/llm_world_modifier.cpython-314.pyc`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 8937 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F114: `src/runtime/nodes/llm_answer.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 4326 bytes
- **Key symbols:** functions: _get_emitter, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F115: `src/runtime/nodes/llm_context_builder.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 9379 bytes
- **Key symbols:** functions: _ensure_list, _get_emitter, _merge_context_obj, _merge_notes, _parse_first_json_object, make; constants: GROUP, LABEL, MAX_CONTEXT_ROUNDS, NODE_ID, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F116: `src/runtime/nodes/llm_memory_retriever.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 8352 bytes
- **Key symbols:** functions: _get_emitter, _parse_first_json_object, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F117: `src/runtime/nodes/llm_memory_writer.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 7178 bytes
- **Key symbols:** functions: _get_emitter, _parse_first_json_object, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F118: `src/runtime/nodes/llm_reflect_topics.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 4550 bytes
- **Key symbols:** functions: _coerce_topics, _get_emitter, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F119: `src/runtime/nodes/llm_router.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 3875 bytes
- **Key symbols:** functions: _get_emitter, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F120: `src/runtime/nodes/llm_world_modifier.py`
- **Purpose:** LangGraph LLM node implementation and NodeSpec registration.
- **Size:** 6961 bytes
- **Key symbols:** functions: _get_emitter, _parse_first_json_object, make; constants: GROUP, LABEL, NODE_ID, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** —
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.prompting, runtime.providers.types, runtime.registry, runtime.services, runtime.state, runtime.tool_loop
- **Notes/risks:** —
### F121: `src/runtime/prompt_loader.py`
- **Purpose:** Loads prompt text files from resources/prompts by name.
- **Size:** 203 bytes
- **Key symbols:** functions: load_prompt_text
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F122: `src/runtime/prompting.py`
- **Purpose:** Token rendering for prompt templates and prompt-size logging.
- **Size:** 433 bytes
- **Key symbols:** functions: render_tokens
- **Inbound deps:** runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier
- **Outbound deps:** —
- **Notes/risks:** —
### F123: `src/runtime/providers/__pycache__/base.cpython-311.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 3314 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F124: `src/runtime/providers/__pycache__/base.cpython-314.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 4000 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F125: `src/runtime/providers/__pycache__/factory.cpython-311.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 936 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F126: `src/runtime/providers/__pycache__/factory.cpython-314.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 964 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F127: `src/runtime/providers/__pycache__/ollama.cpython-311.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 13656 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F128: `src/runtime/providers/__pycache__/ollama.cpython-314.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 15179 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F129: `src/runtime/providers/__pycache__/types.cpython-311.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 6254 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F130: `src/runtime/providers/__pycache__/types.cpython-314.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 5370 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F131: `src/runtime/providers/__pycache__/validate.cpython-311.pyc`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 1935 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F132: `src/runtime/providers/base.py`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 1823 bytes
- **Key symbols:** classes: LLMProvider, ProviderError
- **Inbound deps:** runtime.deps, runtime.tool_loop
- **Outbound deps:** —
- **Notes/risks:** —
### F133: `src/runtime/providers/factory.py`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 373 bytes
- **Key symbols:** functions: make_provider
- **Inbound deps:** runtime.deps
- **Outbound deps:** —
- **Notes/risks:** —
### F134: `src/runtime/providers/ollama.py`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 10919 bytes
- **Key symbols:** classes: OllamaProvider; functions: _http_json, _http_jsonl_stream, _to_ollama_messages, _to_ollama_tools
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F135: `src/runtime/providers/types.py`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 2928 bytes
- **Key symbols:** classes: ChatParams, ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse, Message, ModelInfo, StreamEvent, ToolCall, ToolDef, Usage
- **Inbound deps:** runtime.deps, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.tool_loop, runtime.tools.definitions.chat_history_tail, runtime.tools.definitions.memory_query, runtime.tools.definitions.memory_store, runtime.tools.definitions.world_apply_ops, runtime.tools.providers.static_provider, runtime.tools.registry
- **Outbound deps:** —
- **Notes/risks:** —
### F136: `src/runtime/providers/validate.py`
- **Purpose:** LLM provider abstraction or provider implementation.
- **Size:** 876 bytes
- **Key symbols:** classes: RequiredModel; functions: validate_models_installed
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F137: `src/runtime/registry.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 976 bytes
- **Key symbols:** classes: NodeSpec; functions: get, register
- **Inbound deps:** runtime.build, runtime.graph_build, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier
- **Outbound deps:** runtime.deps, runtime.services, runtime.state
- **Notes/risks:** —
### F138: `src/runtime/services.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 556 bytes
- **Key symbols:** classes: RuntimeServices
- **Inbound deps:** controller.runtime_services, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry
- **Outbound deps:** runtime.tools.resources, runtime.tools.toolkit
- **Notes/risks:** —
### F139: `src/runtime/skills/__pycache__/registry.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 421 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F140: `src/runtime/skills/catalog/__pycache__/core_context.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 422 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F141: `src/runtime/skills/catalog/__pycache__/core_world.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 407 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F142: `src/runtime/skills/catalog/__pycache__/mcp_memory_read.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 414 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F143: `src/runtime/skills/catalog/__pycache__/mcp_memory_write.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 416 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F144: `src/runtime/skills/catalog/core_context.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 349 bytes
- **Key symbols:** constants: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F145: `src/runtime/skills/catalog/core_world.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 113 bytes
- **Key symbols:** constants: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F146: `src/runtime/skills/catalog/mcp_memory_read.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 114 bytes
- **Key symbols:** constants: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F147: `src/runtime/skills/catalog/mcp_memory_write.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 115 bytes
- **Key symbols:** constants: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F148: `src/runtime/skills/registry.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 355 bytes
- **Key symbols:** constants: ENABLED_SKILLS
- **Inbound deps:** runtime.tools.toolkit
- **Outbound deps:** —
- **Notes/risks:** —
### F149: `src/runtime/state.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1343 bytes
- **Key symbols:** classes: RuntimeContext, RuntimeFinal, RuntimeRuntime, RuntimeState, RuntimeTask; functions: new_runtime_state
- **Inbound deps:** controller.worker, runtime.build, runtime.graph_build, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry
- **Outbound deps:** —
- **Notes/risks:** —
### F150: `src/runtime/tool_loop.py`
- **Purpose:** Deterministic streaming tool loop: captures tool calls, executes handlers, injects tool results back into chat.
- **Size:** 7971 bytes
- **Key symbols:** classes: ToolSet; functions: _parse_tool_args_json, _stream_provider_once, chat_stream
- **Inbound deps:** runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.tools.bindings.chat_history_tail, runtime.tools.bindings.memory_query, runtime.tools.bindings.memory_store, runtime.tools.providers.static_provider, runtime.tools.registry, runtime.tools.toolkit
- **Outbound deps:** runtime.deps, runtime.emitter, runtime.providers.base, runtime.providers.types
- **Notes/risks:** —
### F151: `src/runtime/tools/__pycache__/registry.cpython-311.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1685 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F152: `src/runtime/tools/__pycache__/resources.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 2147 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F153: `src/runtime/tools/__pycache__/toolkit.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 4307 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F154: `src/runtime/tools/bindings/__pycache__/chat_history_tail.cpython-314.pyc`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 3152 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F155: `src/runtime/tools/bindings/__pycache__/memory_query.cpython-314.pyc`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 7177 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F156: `src/runtime/tools/bindings/__pycache__/memory_store.cpython-314.pyc`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 4557 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F157: `src/runtime/tools/bindings/__pycache__/world_apply_ops.cpython-314.pyc`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 4586 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F158: `src/runtime/tools/bindings/chat_history_tail.py`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 2006 bytes
- **Key symbols:** functions: bind
- **Inbound deps:** —
- **Outbound deps:** runtime.tool_loop, runtime.tools.resources
- **Notes/risks:** —
### F159: `src/runtime/tools/bindings/memory_query.py`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 5457 bytes
- **Key symbols:** functions: _as_dict, _extract_items_from_mcp_result, bind; constants: DEFAULT_OPENMEMORY_SERVER_ID
- **Inbound deps:** —
- **Outbound deps:** runtime.tool_loop, runtime.tools.resources
- **Notes/risks:** —
### F160: `src/runtime/tools/bindings/memory_store.py`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 3564 bytes
- **Key symbols:** functions: bind; constants: DEFAULT_OPENMEMORY_SERVER_ID
- **Inbound deps:** —
- **Outbound deps:** runtime.tool_loop, runtime.tools.resources
- **Notes/risks:** —
### F161: `src/runtime/tools/bindings/world_apply_ops.py`
- **Purpose:** Tool handler binding implementation (executes tool behavior using ToolResources).
- **Size:** 2757 bytes
- **Key symbols:** functions: _apply_op, _get_path, _set_path, bind; constants: ALLOWED_PATHS
- **Inbound deps:** —
- **Outbound deps:** controller.world_state, runtime.tools.resources
- **Notes/risks:** —
### F162: `src/runtime/tools/definitions/__pycache__/chat_history_tail.cpython-314.pyc`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 1052 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F163: `src/runtime/tools/definitions/__pycache__/memory_query.cpython-314.pyc`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 1954 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F164: `src/runtime/tools/definitions/__pycache__/memory_store.cpython-314.pyc`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 1736 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F165: `src/runtime/tools/definitions/__pycache__/world_apply_ops.cpython-314.pyc`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 1131 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F166: `src/runtime/tools/definitions/chat_history_tail.py`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 806 bytes
- **Key symbols:** functions: tool_def
- **Inbound deps:** —
- **Outbound deps:** runtime.providers.types
- **Notes/risks:** —
### F167: `src/runtime/tools/definitions/memory_query.py`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 2658 bytes
- **Key symbols:** functions: tool_def
- **Inbound deps:** —
- **Outbound deps:** runtime.providers.types
- **Notes/risks:** —
### F168: `src/runtime/tools/definitions/memory_store.py`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 2381 bytes
- **Key symbols:** functions: tool_def
- **Inbound deps:** —
- **Outbound deps:** runtime.providers.types
- **Notes/risks:** —
### F169: `src/runtime/tools/definitions/world_apply_ops.py`
- **Purpose:** Tool schema definition (name/description/JSON schema).
- **Size:** 1227 bytes
- **Key symbols:** functions: tool_def
- **Inbound deps:** —
- **Outbound deps:** runtime.providers.types
- **Notes/risks:** —
### F170: `src/runtime/tools/policy/__pycache__/node_skill_policy.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 581 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F171: `src/runtime/tools/policy/node_skill_policy.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 602 bytes
- **Key symbols:** constants: NODE_ALLOWED_SKILLS
- **Inbound deps:** runtime.tools.toolkit
- **Outbound deps:** —
- **Notes/risks:** —
### F172: `src/runtime/tools/providers/__pycache__/static_provider.cpython-314.pyc`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 3012 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F173: `src/runtime/tools/providers/static_provider.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1970 bytes
- **Key symbols:** classes: StaticProvider, StaticTool
- **Inbound deps:** runtime.tools.toolkit
- **Outbound deps:** runtime.providers.types, runtime.tool_loop, runtime.tools.resources
- **Notes/risks:** —
### F174: `src/runtime/tools/registry.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 1067 bytes
- **Key symbols:** functions: build_default_toolset
- **Inbound deps:** —
- **Outbound deps:** runtime.providers.types, runtime.tool_loop
- **Notes/risks:** —
### F175: `src/runtime/tools/resources.py`
- **Purpose:** File present in snapshot; purpose unclear from filename alone.
- **Size:** 826 bytes
- **Key symbols:** classes: ChatHistoryService, MCPClient, ToolResources
- **Inbound deps:** controller.runtime_services, runtime.services, runtime.tools.bindings.chat_history_tail, runtime.tools.bindings.memory_query, runtime.tools.bindings.memory_store, runtime.tools.bindings.world_apply_ops, runtime.tools.providers.static_provider, runtime.tools.toolkit
- **Outbound deps:** —
- **Notes/risks:** —
### F176: `src/runtime/tools/toolkit.py`
- **Purpose:** RuntimeToolkit assembles ToolSets per node using enabled skills and node allowlists.
- **Size:** 2325 bytes
- **Key symbols:** classes: RuntimeToolkit, Skill; functions: _load_skills
- **Inbound deps:** controller.runtime_services, runtime.services
- **Outbound deps:** runtime.skills.registry, runtime.tool_loop, runtime.tools.policy.node_skill_policy, runtime.tools.providers.static_provider, runtime.tools.resources
- **Notes/risks:** —
### F177: `src/tests/__init__.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 75 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F178: `src/tests/__pycache__/__init__.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 158 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F179: `src/tests/__pycache__/__init__.cpython-314.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 166 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F180: `src/tests/__pycache__/chat_history_smoketest.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 5060 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F181: `src/tests/__pycache__/chat_history_smoketest.cpython-314.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4783 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F182: `src/tests/__pycache__/langchain_probe_list_parsers.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 709 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F183: `src/tests/__pycache__/langchain_probe_output_parser.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 2343 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F184: `src/tests/__pycache__/langchain_probe_prompt_template.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 899 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F185: `src/tests/__pycache__/langchain_probe_router_tool_selection.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4868 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F186: `src/tests/__pycache__/langchain_probe_text_splitter.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4805 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F187: `src/tests/__pycache__/langgraph_test.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4964 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F188: `src/tests/__pycache__/langgraph_test_ollama_router.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 7293 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F189: `src/tests/__pycache__/langgraph_test_ollama_router_planner_answer.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 11494 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F190: `src/tests/__pycache__/memory_k_selftest.cpython-314.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 1118 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F191: `src/tests/__pycache__/ollama_chat_interactive.cpython-311.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 5043 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F192: `src/tests/__pycache__/ollama_chat_interactive.cpython-314.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4981 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F193: `src/tests/__pycache__/openmemory_interactive.cpython-314.pyc`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 6046 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F194: `src/tests/chat_history_smoketest.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 2966 bytes
- **Key symbols:** functions: _show_one_turn, run_chat_history_smoketest, run_chat_messages_format_probe
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F195: `src/tests/langchain_probe_list_parsers.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 242 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F196: `src/tests/langchain_probe_output_parser.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 1264 bytes
- **Key symbols:** classes: RouteDecision; functions: main
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F197: `src/tests/langchain_probe_prompt_template.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 465 bytes
- **Key symbols:** functions: main
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F198: `src/tests/langchain_probe_router_tool_selection.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 3275 bytes
- **Key symbols:** classes: RouteAction; functions: call_ollama, main, router_llm; constants: OLLAMA_URL, ROUTER_MODEL, TIMEOUT_S
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F199: `src/tests/langchain_probe_text_splitter.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 570 bytes
- **Key symbols:** functions: main
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F200: `src/tests/langgraph_test.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 2565 bytes
- **Key symbols:** classes: LGState; functions: build_graph, main, node_answer_direct, node_answer_plan, node_route, run_once
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F201: `src/tests/langgraph_test_ollama_router.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 4407 bytes
- **Key symbols:** classes: LGState; functions: build_graph, call_ollama_generate, main, node_answer_direct, node_answer_plan, node_route_llm, parse_router_decision, run_once; constants: OLLAMA_URL, PLANNER_MODEL, ROUTER_MODEL
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F202: `src/tests/langgraph_test_ollama_router_planner_answer.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 7073 bytes
- **Key symbols:** classes: LGState; functions: build_graph, call_ollama_generate, call_ollama_stream, main, node_answer_direct_llm, node_answer_from_plan_llm, node_planner_llm, node_route_llm, parse_router_decision, run_once; constants: CHAT_MODEL, OLLAMA_URL, PLANNER_MODEL, ROUTER_MODEL
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F203: `src/tests/ollama_chat_interactive.py`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 2725 bytes
- **Key symbols:** functions: _post_json, ollama_generate, run_ollama_interactive_chat
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F204: `src/tests/probe_toolcall.json`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 643 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F205: `src/tests/probe_toolcall_jsonmode.json`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 631 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F206: `src/tests/probe_toolresult.json`
- **Purpose:** Probe/test script (developer tooling).
- **Size:** 799 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** —
### F207: `src/ui/__pycache__/chat_renderer.cpython-311.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 18316 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F208: `src/ui/__pycache__/chat_renderer.cpython-314.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 19228 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F209: `src/ui/__pycache__/config_dialog.cpython-311.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 30477 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F210: `src/ui/__pycache__/config_dialog.cpython-314.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 32273 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F211: `src/ui/__pycache__/main_window.cpython-311.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 22805 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F212: `src/ui/__pycache__/main_window.cpython-314.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 24412 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F213: `src/ui/__pycache__/widgets.cpython-311.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 33558 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F214: `src/ui/__pycache__/widgets.cpython-314.pyc`
- **Purpose:** PySide6 UI module.
- **Size:** 35486 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); generated cache artifact (__pycache__)
### F215: `src/ui/chat_renderer.py`
- **Purpose:** PySide6 UI module.
- **Size:** 14411 bytes
- **Key symbols:** classes: ChatRenderer; functions: _split_out_code_fences, format_content_to_html, render_chat_html; constants: HTML_TEMPLATE
- **Inbound deps:** ui.main_window
- **Outbound deps:** —
- **Notes/risks:** —
### F216: `src/ui/config_dialog.py`
- **Purpose:** PySide6 UI module.
- **Size:** 18578 bytes
- **Key symbols:** classes: ConfigDialog, OllamaModelPickerDialog; functions: _parse_ollama_list_models
- **Inbound deps:** ui.main_window
- **Outbound deps:** —
- **Notes/risks:** —
### F217: `src/ui/main_window.py`
- **Purpose:** PySide6 UI module.
- **Size:** 13333 bytes
- **Key symbols:** classes: MainWindow
- **Inbound deps:** —
- **Outbound deps:** ui.chat_renderer, ui.config_dialog, ui.widgets
- **Notes/risks:** —
### F218: `src/ui/widgets.py`
- **Purpose:** PySide6 UI module.
- **Size:** 17994 bytes
- **Key symbols:** classes: BrainWidget, ChatInput, CombinedLogsWindow, ThalamusLogWindow, ThoughtLogWindow, WorldSummaryWidget
- **Inbound deps:** ui.main_window
- **Outbound deps:** —
- **Notes/risks:** —

## var/
### F221: `var/llm-thalamus-dev/data/chat_history.jsonl`
- **Purpose:** Runtime data artifact (dev state/data).
- **Size:** 12592 bytes
- **Key symbols:** (JSON Lines chat history)
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** dev/runtime artifact; consider gitignore for releases
### F222: `var/llm-thalamus-dev/data/episodes.sqlite`
- **Purpose:** Runtime data artifact (dev state/data).
- **Size:** 512000 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); dev/runtime artifact; consider gitignore for releases
### F223: `var/llm-thalamus-dev/data/memory.sqlite`
- **Purpose:** Runtime data artifact (dev state/data).
- **Size:** 684032 bytes
- **Key symbols:** —
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** binary or non-text (inventory based on path/metadata only); dev/runtime artifact; consider gitignore for releases
### F224: `var/llm-thalamus-dev/state/world_state.json`
- **Purpose:** Runtime data artifact (dev state/data).
- **Size:** 382 bytes
- **Key symbols:** (world state JSON data)
- **Inbound deps:** —
- **Outbound deps:** —
- **Notes/risks:** dev/runtime artifact; consider gitignore for releases
