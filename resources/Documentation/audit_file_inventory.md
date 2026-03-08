# llm_thalamus audit file inventory

This file is section 10 of the audit. IDs are stable only for this snapshot.

## Directory: `.`

### F001 — `CONTRIBUTING.md`
- **Purpose:** Contribution guide; appears partly stale relative to current code layout.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** Also appears stale: setup/run commands mention older paths and modules.

### F002 — `LICENSE.md`
- **Purpose:** Project license text.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F003 — `Makefile`
- **Purpose:** System installation/uninstallation recipe for the Python app and runtime resources.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** Installs prompts and config, but comments claim graphics are not installed while the desktop file and UI expect them under /usr/share/llm-thalamus/graphics; this is a packaging mismatch.

### F004 — `README.md`
- **Purpose:** User-facing project overview and usage documentation.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F005 — `README_developer.md`
- **Purpose:** Developer-oriented architecture/process notes; partially stale versus current snapshot.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** References nodes and files that are not present in this snapshot (e.g. router/memory_writer/world_modifier paths); treat as stale design intent, not source of truth.

### F006 — `llm_thalamus.desktop`
- **Purpose:** Desktop launcher metadata for installed environments.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** References /usr/share/llm-thalamus/graphics/llm_thalamus.svg, but Makefile comments say graphics are not installed by this package.

## Directory: `resources/Documentation`

### F007 — `resources/Documentation/Context builder skills.txt`
- **Purpose:** Ad hoc design note about context-builder skills.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F008 — `resources/Documentation/Node_template.py`
- **Purpose:** Template/example for authoring a node module.
- **Key symbols:** functions: make; constants/top-level names: NODE_ID, GROUP, LABEL, PROMPT_NAME, ROLE_KEY
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/registry.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F009 — `resources/Documentation/Prompt_template.txt`
- **Purpose:** Template/example for authoring a prompt file.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F010 — `resources/Documentation/audit_appendix.md`
- **Purpose:** Existing audit appendix bundled in the repo.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** Stale relative to this snapshot.

### F011 — `resources/Documentation/audit_file_inventory.md`
- **Purpose:** Existing file inventory document bundled in the repo.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** Stale relative to this snapshot.

### F012 — `resources/Documentation/audit_overview.md`
- **Purpose:** Existing architecture audit document bundled in the repo.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** Stale relative to this snapshot; it documents a larger node set than is currently shipped.

## Directory: `resources/config`

### F013 — `resources/config/config.json`
- **Purpose:** Shipped configuration template and dev-mode active config.
- **Key symbols:** N/A
- **Inbound deps:** src/config/_load.py, src/config/_schema.py, src/config/__init__.py
- **Outbound deps:** None
- **Notes/risks:** Requires llm.roles.answer, planner, and reflect. Installed-mode graphics path assumes resources are installed under /usr/share/llm-thalamus/graphics.

## Directory: `resources/graphics`

### F014 — `resources/graphics/inactive.jpg`
- **Purpose:** UI asset for inactive brain state.
- **Key symbols:** N/A
- **Inbound deps:** src/ui/widgets.py (BrainWidget) and/or llm_thalamus.desktop
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F015 — `resources/graphics/llm.jpg`
- **Purpose:** UI asset for fully active brain state.
- **Key symbols:** N/A
- **Inbound deps:** src/ui/widgets.py (BrainWidget) and/or llm_thalamus.desktop
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F016 — `resources/graphics/llm_thalamus.svg`
- **Purpose:** Vector logo/icon asset.
- **Key symbols:** N/A
- **Inbound deps:** src/ui/widgets.py (BrainWidget) and/or llm_thalamus.desktop
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F017 — `resources/graphics/thalamus.jpg`
- **Purpose:** UI asset for thalamus-only brain state.
- **Key symbols:** N/A
- **Inbound deps:** src/ui/widgets.py (BrainWidget) and/or llm_thalamus.desktop
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `resources/prompts`

### F018 — `resources/prompts/runtime_answer.txt`
- **Purpose:** Prompt template for the answer node.
- **Key symbols:** N/A
- **Inbound deps:** src/runtime/nodes/llm_answer.py via Deps.load_prompt()
- **Outbound deps:** None
- **Notes/risks:** Very lean prompt; most orchestration burden is intentionally pushed upstream.

### F019 — `resources/prompts/runtime_context_builder.txt`
- **Purpose:** Prompt template for the context-builder controller node.
- **Key symbols:** N/A
- **Inbound deps:** src/runtime/nodes/llm_context_builder.py via Deps.load_prompt()
- **Outbound deps:** None
- **Notes/risks:** Prompt still mentions planner as a possible route, but graph_build currently collapses everything to answer.

### F020 — `resources/prompts/runtime_reflect.txt`
- **Purpose:** Prompt template for the reflect controller node.
- **Key symbols:** N/A
- **Inbound deps:** src/runtime/nodes/llm_reflect.py via Deps.load_prompt()
- **Outbound deps:** None
- **Notes/risks:** Prompt assumes one-tool-per-step behavior, matching the shared controller loop contract.

## Directory: `src/config`

### F021 — `src/config/__init__.py`
- **Purpose:** Public config bootstrap API; produces ConfigSnapshot from CLI args and config files.
- **Key symbols:** classes: ConfigSnapshot; functions: bootstrap_config
- **Inbound deps:** src/llm_thalamus.py
- **Outbound deps:** src/config/_cli.py, src/config/_load.py, src/config/_policy.py, src/config/_rootfind.py, src/config/_schema.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F022 — `src/config/_cli.py`
- **Purpose:** Bootstrap CLI parser for dev/installed mode selection.
- **Key symbols:** classes: BootstrapArgs; functions: _env_truthy, parse_bootstrap_args
- **Inbound deps:** src/config/__init__.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F023 — `src/config/_load.py`
- **Purpose:** Config file loading and installed-mode template copy helpers.
- **Key symbols:** functions: ensure_config_file_exists, load_raw_config_json
- **Inbound deps:** src/config/__init__.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F024 — `src/config/_policy.py`
- **Purpose:** Path policy for dev vs installed layouts and path resolution helpers.
- **Key symbols:** classes: Roots; functions: compute_roots_for_mode, resolve_resource_path, resolve_writable_path, format_mode_summary
- **Inbound deps:** src/config/__init__.py, src/config/_schema.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F025 — `src/config/_rootfind.py`
- **Purpose:** Project-root discovery helper for repo-local launches.
- **Key symbols:** functions: find_project_root
- **Inbound deps:** src/config/__init__.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F026 — `src/config/_schema.py`
- **Purpose:** Schema extraction/normalization from raw JSON config to effective typed values.
- **Key symbols:** classes: EffectiveValues; functions: _get_dict, _get_str, _get_int, _get_float, extract_effective_values
- **Inbound deps:** src/config/__init__.py
- **Outbound deps:** src/config/_policy.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/controller`

### F027 — `src/controller/chat_history.py`
- **Purpose:** Low-level JSONL chat history persistence helpers.
- **Key symbols:** classes: ChatTurn; functions: now_iso_utc, ensure_history_file, _parse_line, read_tail, trim_to_max, append_turn, format_for_prompt; constants/top-level names: Role
- **Inbound deps:** src/controller/chat_history_service.py, src/controller/worker.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F028 — `src/controller/chat_history_service.py`
- **Purpose:** Thin service wrapper exposing history tail reads to tools.
- **Key symbols:** classes: FileChatHistoryService
- **Inbound deps:** src/controller/runtime_services.py
- **Outbound deps:** src/controller/chat_history.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F029 — `src/controller/runtime_services.py`
- **Purpose:** Constructs RuntimeServices, ToolResources, RuntimeToolkit, and optional MCP client.
- **Key symbols:** functions: build_runtime_services
- **Inbound deps:** src/controller/worker.py
- **Outbound deps:** src/controller/chat_history_service.py, src/controller/mcp/client.py, src/runtime/services.py, src/runtime/tools/resources.py, src/runtime/tools/toolkit.py
- **Notes/risks:** This is the main MCP instantiation boundary. Nodes receive only RuntimeServices/ToolResources, not MCP client classes directly.

### F030 — `src/controller/worker.py`
- **Purpose:** Qt worker/controller that owns world state, history persistence, runtime invocation, and UI signal fan-out.
- **Key symbols:** classes: ControllerWorker; functions: _now_iso_local
- **Inbound deps:** src/llm_thalamus.py
- **Outbound deps:** src/controller/chat_history.py, src/controller/runtime_services.py, src/controller/world_state.py, src/runtime/deps.py, src/runtime/langgraph_runner.py, src/runtime/state.py
- **Notes/risks:** Central change amplifier: it touches history, world persistence, runtime execution, and nearly all UI event wiring.

### F031 — `src/controller/world_state.py`
- **Purpose:** Durable world-state defaults, load/reset, and commit helpers.
- **Key symbols:** functions: default_world, load_world_state, commit_world_state; constants/top-level names: World
- **Inbound deps:** src/controller/worker.py, src/runtime/tools/bindings/world_apply_ops.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** load_world_state refreshes updated_at on load, but mutation writes only occur when the controller commits at turn end.

## Directory: `src/controller/mcp`

### F032 — `src/controller/mcp/client.py`
- **Purpose:** Mechanical MCP JSON-RPC client with initialize, tools/list, and tools/call support.
- **Key symbols:** classes: MCPServerConfig, MCPToolCallResult, MCPClient
- **Inbound deps:** src/controller/runtime_services.py
- **Outbound deps:** src/controller/mcp/transport_streamable_http.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F033 — `src/controller/mcp/transport_streamable_http.py`
- **Purpose:** HTTP POST transport for MCP streamable-http servers.
- **Key symbols:** classes: HttpResponse, StreamableHttpTransport
- **Inbound deps:** src/controller/mcp/client.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src`

### F034 — `src/llm_thalamus.py`
- **Purpose:** CLI/module entrypoint that boots config, prints a startup summary, creates the Qt application, and wires controller + main window.
- **Key symbols:** functions: main
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/config/__init__.py, src/controller/worker.py, src/ui/main_window.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/runtime`

### F035 — `src/runtime/__init__.py`
- **Purpose:** Package export marker.
- **Key symbols:** constants/top-level names: __all__
- **Inbound deps:** src/runtime/tools/providers/static_provider.py, src/runtime/tools/toolkit.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F036 — `src/runtime/build.py`
- **Purpose:** Tiny graph build/invoke wrapper; currently largely redundant with langgraph_runner.
- **Key symbols:** functions: build_runtime_graph, run_graph
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/graph_build.py, src/runtime/nodes/__init__.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** Appears unused by the shipped UI path; langgraph_runner builds the graph directly.

### F037 — `src/runtime/deps.py`
- **Purpose:** Runtime dependency assembly: provider construction, role specs, prompt root, and startup model validation.
- **Key symbols:** classes: RoleLLM, RoleSpec, Deps; functions: _get_cfg_value, _chat_params_from_mapping, _validate_required_models_or_die, _normalize_response_format, build_runtime_deps; constants/top-level names: Chunk
- **Inbound deps:** resources/Documentation/Node_template.py, src/controller/worker.py, src/runtime/build.py, src/runtime/langgraph_runner.py, src/runtime/nodes/context_bootstrap.py, src/runtime/nodes/llm_answer.py, src/runtime/nodes/llm_context_builder.py, src/runtime/nodes/llm_reflect.py, src/runtime/registry.py, src/runtime/tool_loop.py
- **Outbound deps:** src/runtime/providers/base.py, src/runtime/providers/factory.py, src/runtime/providers/types.py
- **Notes/risks:** Model startup validation is strict and synchronous; the UI will fail early if configured models are absent.

### F038 — `src/runtime/emitter.py`
- **Purpose:** Node-facing event/span emission helpers for a single turn.
- **Key symbols:** classes: NodeSpan, TurnEmitter
- **Inbound deps:** src/runtime/langgraph_runner.py, src/runtime/nodes_common.py, src/runtime/tool_loop.py
- **Outbound deps:** src/runtime/events.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F039 — `src/runtime/event_bus.py`
- **Purpose:** Thread-safe event queue for streaming turn events across graph execution.
- **Key symbols:** classes: EventBus; constants/top-level names: _SENTINEL
- **Inbound deps:** src/runtime/langgraph_runner.py
- **Outbound deps:** src/runtime/events.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F040 — `src/runtime/events.py`
- **Purpose:** Turn Event Protocol v1 definitions and event factory.
- **Key symbols:** classes: TurnEvent, TurnEventFactory; functions: is_turn_event, assert_turn_event; constants/top-level names: EVENT_PROTOCOL_VERSION, EventType, LogLevel, ThinkingStream, AssistantRole
- **Inbound deps:** src/runtime/emitter.py, src/runtime/event_bus.py, src/runtime/langgraph_runner.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F041 — `src/runtime/graph_build.py`
- **Purpose:** LangGraph construction for the current 4-node pipeline.
- **Key symbols:** functions: build_compiled_graph
- **Inbound deps:** src/runtime/build.py, src/runtime/langgraph_runner.py
- **Outbound deps:** src/runtime/nodes/__init__.py, src/runtime/registry.py, src/runtime/state.py
- **Notes/risks:** Graph currently hard-codes answer as the only real route; planner is reserved in prompt text but not wired into the graph.

### F042 — `src/runtime/graph_policy.py`
- **Purpose:** Leftover routing helper from earlier graph design.
- **Key symbols:** functions: route_after_router
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/state.py
- **Notes/risks:** Appears unused in the current snapshot.

### F043 — `src/runtime/json_extract.py`
- **Purpose:** Fallback utility to extract first JSON object from noisy text.
- **Key symbols:** functions: extract_first_json_object
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F044 — `src/runtime/langgraph_runner.py`
- **Purpose:** Turn runner that builds the graph, installs emitter, streams events, and emits turn/world lifecycle events.
- **Key symbols:** functions: _debug_state_view, _provider_name, run_turn_runtime
- **Inbound deps:** src/controller/worker.py
- **Outbound deps:** src/runtime/deps.py, src/runtime/emitter.py, src/runtime/event_bus.py, src/runtime/events.py, src/runtime/graph_build.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** world_commit delta is computed after the mutable state object has already been mutated by graph execution, so the before/after delta can be inaccurate or empty.

### F045 — `src/runtime/nodes_common.py`
- **Purpose:** Shared node runner utilities: token rendering, streamed text collection, tool prefill, and controller/answer node executors.
- **Key symbols:** classes: TokenSource, TokenBuilder; functions: get_emitter, append_node_trace, bump_counter, stable_json, parse_first_json_object, _compact_text, _compact_tool_args, collect_text, ensure_sources, replace_source_by_kind, as_records, run_tools_mechanically, run_streaming_answer_node, run_structured_node, run_controller_node; constants/top-level names: _TOKEN_RE, GLOBAL_TOKEN_SPEC
- **Inbound deps:** resources/Documentation/Node_template.py, src/runtime/nodes/context_bootstrap.py, src/runtime/nodes/llm_answer.py, src/runtime/nodes/llm_context_builder.py, src/runtime/nodes/llm_reflect.py
- **Outbound deps:** src/runtime/emitter.py, src/runtime/prompting.py, src/runtime/providers/types.py, src/runtime/tool_loop.py
- **Notes/risks:** High-value hotspot: shared token spec, controller loop, answer streaming, and tool-result plumbing all meet here.

### F046 — `src/runtime/prompt_loader.py`
- **Purpose:** Single helper to read a prompt file by path.
- **Key symbols:** functions: load_prompt_text
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Appears unused; deps.load_prompt is the active prompt-loading path.

### F047 — `src/runtime/prompting.py`
- **Purpose:** Token placeholder replacement and unresolved-token checking.
- **Key symbols:** functions: render_tokens; constants/top-level names: _TOKEN_RE
- **Inbound deps:** src/runtime/nodes_common.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F048 — `src/runtime/registry.py`
- **Purpose:** Node registry for declarative node specs.
- **Key symbols:** classes: NodeSpec; functions: register, get; constants/top-level names: _REGISTRY
- **Inbound deps:** resources/Documentation/Node_template.py, src/runtime/graph_build.py, src/runtime/nodes/context_bootstrap.py, src/runtime/nodes/llm_answer.py, src/runtime/nodes/llm_context_builder.py, src/runtime/nodes/llm_reflect.py
- **Outbound deps:** src/runtime/deps.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F049 — `src/runtime/services.py`
- **Purpose:** Small runtime-only services bundle passed into node factories.
- **Key symbols:** classes: RuntimeServices
- **Inbound deps:** resources/Documentation/Node_template.py, src/controller/runtime_services.py, src/runtime/build.py, src/runtime/langgraph_runner.py, src/runtime/nodes/context_bootstrap.py, src/runtime/nodes/llm_answer.py, src/runtime/nodes/llm_context_builder.py, src/runtime/nodes/llm_reflect.py, src/runtime/registry.py
- **Outbound deps:** src/runtime/tools/resources.py, src/runtime/tools/toolkit.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F050 — `src/runtime/state.py`
- **Purpose:** TypedDict sketches and factory for per-turn runtime state.
- **Key symbols:** classes: RuntimeTask, RuntimeFinal, RuntimeRuntime, RuntimeContext, RuntimeState; functions: new_runtime_state; constants/top-level names: State
- **Inbound deps:** resources/Documentation/Node_template.py, src/controller/worker.py, src/runtime/build.py, src/runtime/graph_build.py, src/runtime/graph_policy.py, src/runtime/langgraph_runner.py, src/runtime/nodes/context_bootstrap.py, src/runtime/nodes/llm_answer.py, src/runtime/nodes/llm_context_builder.py, src/runtime/nodes/llm_reflect.py, src/runtime/registry.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** TypedDict sketches under-describe many fields actually written at runtime (turn_id, timestamp, context.sources, reflect metadata, etc.).

### F051 — `src/runtime/tool_loop.py`
- **Purpose:** Deterministic streamed tool loop used by controller nodes.
- **Key symbols:** classes: ToolSet; functions: _parse_tool_args_json, _normalize_tool_result, _validate_tool_result, _emit_llm_request, _stream_provider_once, chat_stream; constants/top-level names: ToolArgs, ToolResult, ToolHandler, ToolValidator
- **Inbound deps:** src/runtime/nodes_common.py, src/runtime/tools/bindings/chat_history_tail.py, src/runtime/tools/bindings/memory_query.py, src/runtime/tools/bindings/memory_store.py, src/runtime/tools/bindings/world_apply_ops.py, src/runtime/tools/providers/static_provider.py, src/runtime/tools/registry.py, src/runtime/tools/toolkit.py
- **Outbound deps:** src/runtime/deps.py, src/runtime/emitter.py, src/runtime/providers/base.py, src/runtime/providers/types.py
- **Notes/risks:** Implements the key tool contract boundary. Tool errors are surfaced back to the model instead of aborting the turn.

## Directory: `src/runtime/nodes`

### F052 — `src/runtime/nodes/__init__.py`
- **Purpose:** Imports node modules so they self-register.
- **Key symbols:** No top-level Python symbols discovered.
- **Inbound deps:** src/runtime/build.py, src/runtime/graph_build.py, src/runtime/nodes/__init__.py
- **Outbound deps:** src/runtime/nodes/__init__.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F053 — `src/runtime/nodes/context_bootstrap.py`
- **Purpose:** Mechanical bootstrap node that prefills chat tail and topic-driven memory recall before the LLM context-builder runs.
- **Key symbols:** functions: _safe_json_loads, _topic_query_from_world, make; constants/top-level names: NODE_ID, GROUP, LABEL, ROLE_KEY
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/registry.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** memory_query results are wrapped differently here than in llm_context_builder (payload wrapper vs payload.items), so context.sources schema is inconsistent across nodes.

### F054 — `src/runtime/nodes/llm_answer.py`
- **Purpose:** Final answer node wrapper around the shared streaming answer runner.
- **Key symbols:** functions: make; constants/top-level names: NODE_ID, GROUP, LABEL, PROMPT_NAME
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/registry.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** Answer node bypasses tools entirely and does not enforce a response format.

### F055 — `src/runtime/nodes/llm_context_builder.py`
- **Purpose:** Main controller node that gathers context, may update world, and decides the next step.
- **Key symbols:** functions: _safe_json_loads, make; constants/top-level names: NODE_ID, GROUP, LABEL, PROMPT_NAME, ROLE_KEY, MAX_CONTEXT_ROUNDS
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/registry.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** Context/tool/world orchestration hotspot. It directly mutates state["world"] from tool results but relies on the controller for final disk commit.

### F056 — `src/runtime/nodes/llm_reflect.py`
- **Purpose:** Post-answer controller node that maintains topics and stores durable memories.
- **Key symbols:** functions: _safe_json_loads, make; constants/top-level names: NODE_ID, GROUP, LABEL, PROMPT_NAME, ROLE_KEY, MAX_REFLECT_ROUNDS
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/registry.py, src/runtime/services.py, src/runtime/state.py
- **Notes/risks:** Stores transient bookkeeping in private state key _reflect_stored_count.

## Directory: `src/runtime/providers`

### F057 — `src/runtime/providers/base.py`
- **Purpose:** Abstract provider interface and ProviderError.
- **Key symbols:** classes: ProviderError, LLMProvider
- **Inbound deps:** src/runtime/deps.py, src/runtime/providers/factory.py, src/runtime/providers/ollama.py, src/runtime/providers/validate.py, src/runtime/tool_loop.py
- **Outbound deps:** src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F058 — `src/runtime/providers/factory.py`
- **Purpose:** Factory that maps provider names to provider implementations.
- **Key symbols:** functions: make_provider
- **Inbound deps:** src/runtime/deps.py
- **Outbound deps:** src/runtime/providers/base.py, src/runtime/providers/ollama.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F059 — `src/runtime/providers/ollama.py`
- **Purpose:** python-ollama backed provider implementation, including streaming/tool-call normalization.
- **Key symbols:** classes: OllamaProvider; functions: _as_dict, _tooldef_to_ollama_tool, _extract_tool_calls_from_message, _chatparams_to_options, _response_format_to_ollama_format
- **Inbound deps:** src/runtime/providers/factory.py
- **Outbound deps:** src/runtime/providers/base.py, src/runtime/providers/types.py
- **Notes/risks:** Provider contains transport, stream normalization, tool-call extraction, and debug-payload generation in one large file.

### F060 — `src/runtime/providers/types.py`
- **Purpose:** Canonical provider-facing dataclasses and protocol types.
- **Key symbols:** classes: ToolDef, ToolCall, Message, Usage, StreamEvent, ChatParams, ChatRequest, ChatResponse, EmbeddingRequest, EmbeddingResponse, ModelInfo; constants/top-level names: Role, EventType, Capability
- **Inbound deps:** src/runtime/deps.py, src/runtime/nodes_common.py, src/runtime/providers/base.py, src/runtime/providers/ollama.py, src/runtime/providers/validate.py, src/runtime/tool_loop.py, src/runtime/tools/definitions/chat_history_tail.py, src/runtime/tools/definitions/memory_query.py, src/runtime/tools/definitions/memory_store.py, src/runtime/tools/definitions/world_apply_ops.py, src/runtime/tools/providers/static_provider.py, src/runtime/tools/registry.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F061 — `src/runtime/providers/validate.py`
- **Purpose:** Simple installed-model validation helpers.
- **Key symbols:** classes: RequiredModel; functions: validate_models_installed
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/base.py, src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/runtime/skills/catalog`

### F062 — `src/runtime/skills/catalog/core_context.py`
- **Purpose:** Skill declaration for chat-history retrieval.
- **Key symbols:** constants/top-level names: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F063 — `src/runtime/skills/catalog/core_world.py`
- **Purpose:** Skill declaration for world mutation.
- **Key symbols:** constants/top-level names: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F064 — `src/runtime/skills/catalog/mcp_memory_read.py`
- **Purpose:** Skill declaration for memory-query access.
- **Key symbols:** constants/top-level names: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F065 — `src/runtime/skills/catalog/mcp_memory_write.py`
- **Purpose:** Skill declaration for memory-store access.
- **Key symbols:** constants/top-level names: SKILL_NAME, TOOL_NAMES
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/runtime/skills`

### F066 — `src/runtime/skills/registry.py`
- **Purpose:** Enabled-skill allowlist.
- **Key symbols:** constants/top-level names: ENABLED_SKILLS
- **Inbound deps:** src/runtime/tools/toolkit.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Simple allowlist; no dynamic discovery.

## Directory: `src/runtime/tools/bindings`

### F067 — `src/runtime/tools/bindings/chat_history_tail.py`
- **Purpose:** chat_history_tail implementation over ChatHistoryService.
- **Key symbols:** functions: bind
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/tool_loop.py, src/runtime/tools/resources.py
- **Notes/risks:** The trimming rule checks for role=="user", but persisted chat history uses roles "human" and "you"; that branch will never fire against current controller data.

### F068 — `src/runtime/tools/bindings/memory_query.py`
- **Purpose:** memory_query implementation over MCP openmemory_query.
- **Key symbols:** functions: _as_dict, _extract_items_from_mcp_result, bind; constants/top-level names: DEFAULT_OPENMEMORY_SERVER_ID
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/tool_loop.py, src/runtime/tools/resources.py
- **Notes/risks:** Hard-codes the OpenMemory MCP tool name openmemory_query and injects user_id mechanically from config.

### F069 — `src/runtime/tools/bindings/memory_store.py`
- **Purpose:** memory_store implementation over MCP openmemory_store.
- **Key symbols:** functions: bind; constants/top-level names: DEFAULT_OPENMEMORY_SERVER_ID
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/tool_loop.py, src/runtime/tools/resources.py
- **Notes/risks:** Coerces factual/both requests without facts back to contextual before calling MCP.

### F070 — `src/runtime/tools/bindings/world_apply_ops.py`
- **Purpose:** world_apply_ops implementation over the durable world_state JSON file.
- **Key symbols:** functions: bind, _apply_op, _set_path, _get_path; constants/top-level names: ALLOWED_PATHS
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/controller/world_state.py, src/runtime/tool_loop.py, src/runtime/tools/resources.py
- **Notes/risks:** Despite its name, it does not persist to disk; it loads a world snapshot, applies ops in memory, and returns it. Because it reloads from disk each call, multiple world_apply_ops calls in one turn can lose prior in-memory updates before final commit.

## Directory: `src/runtime/tools/definitions`

### F071 — `src/runtime/tools/definitions/chat_history_tail.py`
- **Purpose:** Schema declaration for chat_history_tail.
- **Key symbols:** functions: tool_def
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F072 — `src/runtime/tools/definitions/memory_query.py`
- **Purpose:** Schema declaration for memory_query.
- **Key symbols:** functions: tool_def
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F073 — `src/runtime/tools/definitions/memory_store.py`
- **Purpose:** Schema declaration for memory_store.
- **Key symbols:** functions: tool_def
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F074 — `src/runtime/tools/definitions/world_apply_ops.py`
- **Purpose:** Schema declaration for world_apply_ops.
- **Key symbols:** functions: tool_def
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/types.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/runtime/tools/policy`

### F075 — `src/runtime/tools/policy/node_skill_policy.py`
- **Purpose:** Node-to-skill capability firewall.
- **Key symbols:** constants/top-level names: NODE_ALLOWED_SKILLS
- **Inbound deps:** src/runtime/tools/toolkit.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/runtime/tools/providers`

### F076 — `src/runtime/tools/providers/static_provider.py`
- **Purpose:** In-process tool provider that binds definitions and handlers from local modules.
- **Key symbols:** classes: StaticTool, StaticProvider; functions: _require_object, _validate_source_object, _validate_ok_object
- **Inbound deps:** src/runtime/tools/toolkit.py
- **Outbound deps:** src/runtime/__init__.py, src/runtime/providers/types.py, src/runtime/tool_loop.py, src/runtime/tools/resources.py
- **Notes/risks:** Good MCP isolation point: all tool definitions + bindings converge here before nodes see them.

## Directory: `src/runtime/tools`

### F077 — `src/runtime/tools/registry.py`
- **Purpose:** Standalone default/echo toolset used for spikes or capability testing.
- **Key symbols:** functions: build_default_toolset
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** src/runtime/providers/types.py, src/runtime/tool_loop.py
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F078 — `src/runtime/tools/resources.py`
- **Purpose:** Protocols and data bundle for tool bindings.
- **Key symbols:** classes: ChatHistoryService, MCPClient, ToolResources
- **Inbound deps:** src/controller/runtime_services.py, src/runtime/services.py, src/runtime/tools/bindings/chat_history_tail.py, src/runtime/tools/bindings/memory_query.py, src/runtime/tools/bindings/memory_store.py, src/runtime/tools/bindings/world_apply_ops.py, src/runtime/tools/providers/static_provider.py, src/runtime/tools/toolkit.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F079 — `src/runtime/tools/toolkit.py`
- **Purpose:** Per-node toolset assembler using skill registry, policy, and static provider.
- **Key symbols:** classes: Skill, RuntimeToolkit; functions: _load_skills
- **Inbound deps:** src/controller/runtime_services.py, src/runtime/services.py
- **Outbound deps:** src/runtime/__init__.py, src/runtime/skills/registry.py, src/runtime/tool_loop.py, src/runtime/tools/policy/node_skill_policy.py, src/runtime/tools/providers/static_provider.py, src/runtime/tools/resources.py
- **Notes/risks:** Static, explicit skill loading keeps behavior predictable but requires code edits for every new skill.

## Directory: `src/tests`

### F080 — `src/tests/__init__.py`
- **Purpose:** Marker/comment for manual test helpers.
- **Key symbols:** No top-level Python symbols discovered.
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F081 — `src/tests/chat_history_smoketest.py`
- **Purpose:** Manual smoke test for chat history persistence; appears to target an older package path.
- **Key symbols:** functions: run_chat_history_smoketest, _show_one_turn, run_chat_messages_format_probe
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Imports chat_history.message_history, which does not exist in this snapshot; likely stale/broken.

### F082 — `src/tests/langchain_probe_list_parsers.py`
- **Purpose:** Probe script to inspect LangChain parser exports.
- **Key symbols:** constants/top-level names: names
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F083 — `src/tests/langchain_probe_output_parser.py`
- **Purpose:** Probe script for LangChain PydanticOutputParser formatting.
- **Key symbols:** classes: RouteDecision; functions: main
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F084 — `src/tests/langchain_probe_prompt_template.py`
- **Purpose:** Probe script for LangChain PromptTemplate rendering.
- **Key symbols:** functions: main
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F085 — `src/tests/langchain_probe_router_tool_selection.py`
- **Purpose:** Experimental script probing router/tool-selection prompting against Ollama.
- **Key symbols:** classes: RouteAction; functions: call_ollama, router_llm, main; constants/top-level names: OLLAMA_URL, ROUTER_MODEL, TIMEOUT_S, parser
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F086 — `src/tests/langchain_probe_text_splitter.py`
- **Purpose:** Probe script for RecursiveCharacterTextSplitter behavior.
- **Key symbols:** functions: main
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F087 — `src/tests/langgraph_test.py`
- **Purpose:** Minimal LangGraph branching prototype.
- **Key symbols:** classes: LGState; functions: node_route, node_answer_direct, node_answer_plan, build_graph, run_once, main
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F088 — `src/tests/langgraph_test_ollama_router.py`
- **Purpose:** LangGraph + Ollama routing prototype.
- **Key symbols:** classes: LGState; functions: call_ollama_generate, parse_router_decision, node_route_llm, node_answer_direct, node_answer_plan, build_graph, run_once, main; constants/top-level names: OLLAMA_URL, ROUTER_MODEL, PLANNER_MODEL
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F089 — `src/tests/langgraph_test_ollama_router_planner_answer.py`
- **Purpose:** LangGraph + Ollama router/planner/answer prototype.
- **Key symbols:** classes: LGState; functions: call_ollama_generate, call_ollama_stream, parse_router_decision, node_route_llm, node_answer_direct_llm, node_planner_llm, node_answer_from_plan_llm, build_graph, run_once, main; constants/top-level names: OLLAMA_URL, ROUTER_MODEL, PLANNER_MODEL, CHAT_MODEL
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F090 — `src/tests/ollama_chat_interactive.py`
- **Purpose:** Interactive/manual raw Ollama chat client script.
- **Key symbols:** functions: _post_json, ollama_generate, run_ollama_interactive_chat
- **Inbound deps:** No internal Python importers found from static scan.
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F091 — `src/tests/probe_toolcall.json`
- **Purpose:** Static probe payload for testing provider tool-call behavior.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F092 — `src/tests/probe_toolcall_jsonmode.json`
- **Purpose:** Static probe payload for tool-call behavior under JSON mode.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

### F093 — `src/tests/probe_toolresult.json`
- **Purpose:** Static probe payload for assistant/tool-result follow-up behavior.
- **Key symbols:** N/A
- **Inbound deps:** Unknown/non-code
- **Outbound deps:** None
- **Notes/risks:** No special risk noted beyond normal maintenance concerns.

## Directory: `src/ui`

### F094 — `src/ui/chat_renderer.py`
- **Purpose:** Markdown/HTML chat rendering widget with streaming assistant updates.
- **Key symbols:** classes: ChatRenderer; functions: _split_out_code_fences, format_content_to_html, render_chat_html; constants/top-level names: _md, HTML_TEMPLATE
- **Inbound deps:** src/ui/main_window.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Depends on Qt WebEngine and markdown-it plugin stack; render issues will surface here, not in the core runtime.

### F095 — `src/ui/config_dialog.py`
- **Purpose:** Qt config editor dialog, including live Ollama model listing.
- **Key symbols:** classes: OllamaModelPickerDialog, ConfigDialog; functions: _parse_ollama_list_models
- **Inbound deps:** src/ui/main_window.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Long UI form builder with direct JSON editing semantics; likely another change amplifier for config schema changes.

### F096 — `src/ui/main_window.py`
- **Purpose:** Primary application window tying chat, brain visual, world panel, and logs together.
- **Key symbols:** classes: MainWindow
- **Inbound deps:** src/llm_thalamus.py
- **Outbound deps:** src/ui/chat_renderer.py, src/ui/config_dialog.py, src/ui/widgets.py
- **Notes/risks:** Large UI composition and signal-wiring hotspot; also owns debug window buffer management.

### F097 — `src/ui/widgets.py`
- **Purpose:** Shared Qt widgets and log windows used by the main UI.
- **Key symbols:** classes: ChatInput, BrainWidget, WorldSummaryWidget, ThalamusLogWindow, ThoughtLogWindow, CombinedLogsWindow
- **Inbound deps:** src/ui/main_window.py
- **Outbound deps:** No internal Python imports found from static scan.
- **Notes/risks:** Mixed collection of unrelated widgets/log windows increases coupling inside one file.

## Directory: `var/llm-thalamus-dev/data`

### F098 — `var/llm-thalamus-dev/data/chat_history.jsonl`
- **Purpose:** Sample/dev chat history persisted by the controller.
- **Key symbols:** N/A
- **Inbound deps:** src/controller/worker.py and related persistence helpers
- **Outbound deps:** None
- **Notes/risks:** Contains user/dev data, not code; useful as a schema example.

## Directory: `var/llm-thalamus-dev/state`

### F099 — `var/llm-thalamus-dev/state/world_state.json`
- **Purpose:** Sample/dev durable world state file.
- **Key symbols:** N/A
- **Inbound deps:** src/controller/worker.py and related persistence helpers
- **Outbound deps:** None
- **Notes/risks:** Contains user/dev data, not code; useful as a schema example.