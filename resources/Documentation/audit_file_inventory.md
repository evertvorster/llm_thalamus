# llm_thalamus Audit — Per-File Inventory (Section 10)

### F001

* **Path:** `CONTRIBUTING.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # Contributing to LLM Thalamus

### F002

* **Path:** `LICENSE.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** GNU GENERAL PUBLIC LICENSE

### F003

* **Path:** `Makefile`
* **Purpose:** Project metadata or miscellaneous asset.

### F004

* **Path:** `README.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # llm_thalamus

### F005

* **Path:** `README_developer.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # llm_thalamus — Developer README

### F006

* **Path:** `llm_thalamus.desktop`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** [Desktop Entry]

### F007

* **Path:** `resources/Documentation/Node_template.py`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** runtime.deps.Deps, runtime.emitter.TurnEmitter, runtime.prompting.render_tokens, runtime.providers.types.Message, runtime.registry.NodeSpec, runtime.registry.register, runtime.state.State, runtime.tool_loop.ToolSet, runtime.tool_loop.chat_stream

### F008

* **Path:** `resources/Documentation/Prompt_template.txt`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # <PROMPT TEMPLATE>

### F009

* **Path:** `resources/Documentation/audit_appendix.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # Audit Appendix

### F010

* **Path:** `resources/Documentation/audit_file_inventory.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # 10) Per-File Inventory (complete)

### F011

* **Path:** `resources/Documentation/audit_overview.md`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key contents:** # llm_thalamus Architecture & Codebase Audit (Snapshot)

### F012

* **Path:** `resources/config/config.json`
* **Purpose:** Default/config template files.
* **Key contents:** {

### F013

* **Path:** `resources/graphics/inactive.jpg`
* **Purpose:** Project metadata or miscellaneous asset.

### F014

* **Path:** `resources/graphics/llm.jpg`
* **Purpose:** Project metadata or miscellaneous asset.

### F015

* **Path:** `resources/graphics/llm_thalamus.svg`
* **Purpose:** Project metadata or miscellaneous asset.

### F016

* **Path:** `resources/graphics/thalamus.jpg`
* **Purpose:** Project metadata or miscellaneous asset.

### F017

* **Path:** `resources/prompts/runtime_answer.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** You are the coherent mind of a persistent local intelligence companion to the user.

### F018

* **Path:** `resources/prompts/runtime_context_builder.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** You are running inside llm_thalamus as node <<NODE_ID>> (role key: <<ROLE_KEY>>).

### F019

* **Path:** `resources/prompts/runtime_memory_retriever.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** [SYSTEM]

### F020

* **Path:** `resources/prompts/runtime_memory_writer.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** [SYSTEM]

### F021

* **Path:** `resources/prompts/runtime_reflect_topics.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** You are the semantic indexer for the user’s local intelligence companion.

### F022

* **Path:** `resources/prompts/runtime_router.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** You are an orchestrator with access to auxiliary state beyond WORLD,

### F023

* **Path:** `resources/prompts/runtime_world_modifier.txt`
* **Purpose:** Prompt templates for runtime LLM nodes.
* **Key contents:** [SYSTEM]

### F024

* **Path:** `src/__pycache__/llm_thalamus.cpython-311.pyc`
* **Purpose:** Project metadata or miscellaneous asset.

### F025

* **Path:** `src/config/__init__.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F026

* **Path:** `src/config/__pycache__/__init__.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F027

* **Path:** `src/config/__pycache__/__init__.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F028

* **Path:** `src/config/__pycache__/_cli.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F029

* **Path:** `src/config/__pycache__/_cli.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F030

* **Path:** `src/config/__pycache__/_load.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F031

* **Path:** `src/config/__pycache__/_load.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F032

* **Path:** `src/config/__pycache__/_policy.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F033

* **Path:** `src/config/__pycache__/_policy.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F034

* **Path:** `src/config/__pycache__/_rootfind.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F035

* **Path:** `src/config/__pycache__/_rootfind.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F036

* **Path:** `src/config/__pycache__/_schema.cpython-311.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F037

* **Path:** `src/config/__pycache__/_schema.cpython-314.pyc`
* **Purpose:** Configuration loading/schema/policy utilities.

### F038

* **Path:** `src/config/_cli.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F039

* **Path:** `src/config/_load.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F040

* **Path:** `src/config/_policy.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F041

* **Path:** `src/config/_rootfind.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F042

* **Path:** `src/config/_schema.py`
* **Purpose:** Configuration loading/schema/policy utilities.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F043

* **Path:** `src/controller/__pycache__/chat_history.cpython-311.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F044

* **Path:** `src/controller/__pycache__/chat_history.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F045

* **Path:** `src/controller/__pycache__/chat_history_service.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F046

* **Path:** `src/controller/__pycache__/runtime_services.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F047

* **Path:** `src/controller/__pycache__/worker.cpython-311.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F048

* **Path:** `src/controller/__pycache__/worker.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F049

* **Path:** `src/controller/__pycache__/world_state.cpython-311.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F050

* **Path:** `src/controller/__pycache__/world_state.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F051

* **Path:** `src/controller/chat_history.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.chat_history_service, controller.worker
* **Outbound deps:** none

### F052

* **Path:** `src/controller/chat_history_service.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.runtime_services
* **Outbound deps:** controller.chat_history.ChatTurn, controller.chat_history.read_tail

### F053

* **Path:** `src/controller/mcp/__pycache__/client.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F054

* **Path:** `src/controller/mcp/__pycache__/transport_streamable_http.cpython-314.pyc`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).

### F055

* **Path:** `src/controller/mcp/client.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.runtime_services
* **Outbound deps:** controller.mcp.transport_streamable_http.StreamableHttpTransport

### F056

* **Path:** `src/controller/mcp/transport_streamable_http.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.mcp.client
* **Outbound deps:** none

### F057

* **Path:** `src/controller/runtime_services.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.worker
* **Outbound deps:** controller.chat_history_service.FileChatHistoryService, controller.mcp.client.MCPClient, controller.mcp.client.MCPServerConfig, runtime.services.RuntimeServices, runtime.tools.resources.ToolResources, runtime.tools.toolkit.RuntimeToolkit

### F058

* **Path:** `src/controller/worker.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** llm_thalamus
* **Outbound deps:** controller.chat_history.append_turn, controller.chat_history.read_tail, controller.runtime_services.build_runtime_services, controller.world_state.commit_world_state, controller.world_state.load_world_state, runtime.deps.build_runtime_deps, runtime.langgraph_runner.run_turn_runtime, runtime.state.new_runtime_state

### F059

* **Path:** `src/controller/world_state.py`
* **Purpose:** Controller layer bridging UI ↔ runtime (chat history, world state, MCP wiring).
* **Key symbols:** n/a
* **Inbound deps:** controller.worker, runtime.tools.bindings.world_apply_ops
* **Outbound deps:** none

### F060

* **Path:** `src/llm_thalamus.py`
* **Purpose:** Project metadata or miscellaneous asset.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** config.bootstrap_config, controller.worker.ControllerWorker, ui.main_window.MainWindow

### F061

* **Path:** `src/runtime/__init__.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F062

* **Path:** `src/runtime/__pycache__/__init__.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F063

* **Path:** `src/runtime/__pycache__/__init__.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F064

* **Path:** `src/runtime/__pycache__/build.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F065

* **Path:** `src/runtime/__pycache__/build.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F066

* **Path:** `src/runtime/__pycache__/deps.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F067

* **Path:** `src/runtime/__pycache__/deps.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F068

* **Path:** `src/runtime/__pycache__/emitter.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F069

* **Path:** `src/runtime/__pycache__/emitter.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F070

* **Path:** `src/runtime/__pycache__/event_bus.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F071

* **Path:** `src/runtime/__pycache__/event_bus.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F072

* **Path:** `src/runtime/__pycache__/events.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F073

* **Path:** `src/runtime/__pycache__/events.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F074

* **Path:** `src/runtime/__pycache__/graph_build.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F075

* **Path:** `src/runtime/__pycache__/graph_build.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F076

* **Path:** `src/runtime/__pycache__/graph_nodes.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F077

* **Path:** `src/runtime/__pycache__/graph_nodes.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F078

* **Path:** `src/runtime/__pycache__/graph_policy.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F079

* **Path:** `src/runtime/__pycache__/graph_policy.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F080

* **Path:** `src/runtime/__pycache__/json_extract.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F081

* **Path:** `src/runtime/__pycache__/json_extract.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F082

* **Path:** `src/runtime/__pycache__/langgraph_runner.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F083

* **Path:** `src/runtime/__pycache__/langgraph_runner.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F084

* **Path:** `src/runtime/__pycache__/nodes_common.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F085

* **Path:** `src/runtime/__pycache__/prompt_loader.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F086

* **Path:** `src/runtime/__pycache__/prompting.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F087

* **Path:** `src/runtime/__pycache__/prompting.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F088

* **Path:** `src/runtime/__pycache__/registry.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F089

* **Path:** `src/runtime/__pycache__/registry.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F090

* **Path:** `src/runtime/__pycache__/run.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F091

* **Path:** `src/runtime/__pycache__/services.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F092

* **Path:** `src/runtime/__pycache__/state.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F093

* **Path:** `src/runtime/__pycache__/state.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F094

* **Path:** `src/runtime/__pycache__/tool_loop.cpython-311.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F095

* **Path:** `src/runtime/__pycache__/tool_loop.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F096

* **Path:** `src/runtime/build.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** runtime.deps.Deps, runtime.nodes, runtime.registry.get, runtime.state.State

### F097

* **Path:** `src/runtime/deps.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** controller.worker, resources/Documentation/Node_template.py, runtime.build, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry, runtime.tool_loop
* **Outbound deps:** runtime.providers.base.LLMProvider, runtime.providers.factory.make_provider, runtime.providers.types.ChatParams, runtime.providers.types.ChatRequest, runtime.providers.types.Message

### F098

* **Path:** `src/runtime/emitter.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** resources/Documentation/Node_template.py, runtime.langgraph_runner, runtime.nodes_common, runtime.tool_loop
* **Outbound deps:** runtime.events.LogLevel, runtime.events.TurnEvent, runtime.events.TurnEventFactory

### F099

* **Path:** `src/runtime/event_bus.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.langgraph_runner
* **Outbound deps:** runtime.events.TurnEvent

### F100

* **Path:** `src/runtime/events.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.emitter, runtime.event_bus, runtime.langgraph_runner
* **Outbound deps:** none

### F101

* **Path:** `src/runtime/graph_build.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.langgraph_runner
* **Outbound deps:** runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry.get, runtime.state.State

### F102

* **Path:** `src/runtime/graph_nodes.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F103

* **Path:** `src/runtime/graph_policy.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F104

* **Path:** `src/runtime/json_extract.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F105

* **Path:** `src/runtime/langgraph_runner.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** controller.worker
* **Outbound deps:** runtime.deps.Deps, runtime.emitter.TurnEmitter, runtime.event_bus.EventBus, runtime.events.TurnEvent, runtime.events.TurnEventFactory, runtime.graph_build.build_compiled_graph, runtime.services.RuntimeServices, runtime.state.State

### F106

* **Path:** `src/runtime/nodes/__init__.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F107

* **Path:** `src/runtime/nodes/__pycache__/__init__.cpython-311.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F108

* **Path:** `src/runtime/nodes/__pycache__/__init__.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F109

* **Path:** `src/runtime/nodes/__pycache__/llm_answer.cpython-311.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F110

* **Path:** `src/runtime/nodes/__pycache__/llm_answer.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F111

* **Path:** `src/runtime/nodes/__pycache__/llm_context_builder.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F112

* **Path:** `src/runtime/nodes/__pycache__/llm_memory_retriever.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F113

* **Path:** `src/runtime/nodes/__pycache__/llm_memory_writer.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F114

* **Path:** `src/runtime/nodes/__pycache__/llm_reflect_topics.cpython-311.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F115

* **Path:** `src/runtime/nodes/__pycache__/llm_reflect_topics.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F116

* **Path:** `src/runtime/nodes/__pycache__/llm_router.cpython-311.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F117

* **Path:** `src/runtime/nodes/__pycache__/llm_router.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F118

* **Path:** `src/runtime/nodes/__pycache__/llm_world_modifier.cpython-314.pyc`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).

### F119

* **Path:** `src/runtime/nodes/llm_answer.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.run_streaming_answer_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F120

* **Path:** `src/runtime/nodes/llm_context_builder.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.as_records, runtime.nodes_common.replace_source_by_kind, runtime.nodes_common.run_controller_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F121

* **Path:** `src/runtime/nodes/llm_memory_retriever.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.run_structured_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F122

* **Path:** `src/runtime/nodes/llm_memory_writer.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.run_structured_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F123

* **Path:** `src/runtime/nodes/llm_reflect_topics.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.run_structured_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F124

* **Path:** `src/runtime/nodes/llm_router.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.get_emitter, runtime.nodes_common.run_structured_node, runtime.nodes_common.run_tools_mechanically, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F125

* **Path:** `src/runtime/nodes/llm_world_modifier.py`
* **Purpose:** Runtime node implementation (LangGraph StateGraph node).
* **Key symbols:** n/a
* **Inbound deps:** runtime.graph_build
* **Outbound deps:** runtime.deps.Deps, runtime.nodes_common.parse_first_json_object, runtime.nodes_common.run_controller_node, runtime.nodes_common.stable_json, runtime.registry.NodeSpec, runtime.registry.register, runtime.services.RuntimeServices, runtime.state.State

### F126

* **Path:** `src/runtime/nodes_common.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier
* **Outbound deps:** runtime.emitter.TurnEmitter, runtime.prompting.render_tokens, runtime.providers.types.Message, runtime.providers.types.StreamEvent, runtime.tool_loop.ToolSet, runtime.tool_loop.chat_stream

### F127

* **Path:** `src/runtime/prompt_loader.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F128

* **Path:** `src/runtime/prompting.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** resources/Documentation/Node_template.py, runtime.nodes_common
* **Outbound deps:** none

### F129

* **Path:** `src/runtime/providers/__pycache__/base.cpython-311.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F130

* **Path:** `src/runtime/providers/__pycache__/base.cpython-314.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F131

* **Path:** `src/runtime/providers/__pycache__/factory.cpython-311.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F132

* **Path:** `src/runtime/providers/__pycache__/factory.cpython-314.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F133

* **Path:** `src/runtime/providers/__pycache__/ollama.cpython-311.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F134

* **Path:** `src/runtime/providers/__pycache__/ollama.cpython-314.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F135

* **Path:** `src/runtime/providers/__pycache__/types.cpython-311.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F136

* **Path:** `src/runtime/providers/__pycache__/types.cpython-314.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F137

* **Path:** `src/runtime/providers/__pycache__/validate.cpython-311.pyc`
* **Purpose:** LLM provider abstraction and implementations.

### F138

* **Path:** `src/runtime/providers/base.py`
* **Purpose:** LLM provider abstraction and implementations.
* **Key symbols:** n/a
* **Inbound deps:** runtime.deps, runtime.tool_loop
* **Outbound deps:** none

### F139

* **Path:** `src/runtime/providers/factory.py`
* **Purpose:** LLM provider abstraction and implementations.
* **Key symbols:** n/a
* **Inbound deps:** runtime.deps
* **Outbound deps:** none

### F140

* **Path:** `src/runtime/providers/ollama.py`
* **Purpose:** LLM provider abstraction and implementations.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F141

* **Path:** `src/runtime/providers/types.py`
* **Purpose:** LLM provider abstraction and implementations.
* **Key symbols:** n/a
* **Inbound deps:** resources/Documentation/Node_template.py, runtime.deps, runtime.nodes_common, runtime.tool_loop, runtime.tools.definitions.chat_history_tail, runtime.tools.definitions.memory_query, runtime.tools.definitions.memory_store, runtime.tools.definitions.world_apply_ops, runtime.tools.providers.static_provider, runtime.tools.registry
* **Outbound deps:** none

### F142

* **Path:** `src/runtime/providers/validate.py`
* **Purpose:** LLM provider abstraction and implementations.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F143

* **Path:** `src/runtime/registry.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** resources/Documentation/Node_template.py, runtime.build, runtime.graph_build, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier
* **Outbound deps:** runtime.deps.Deps, runtime.services.RuntimeServices, runtime.state.State

### F144

* **Path:** `src/runtime/services.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** controller.runtime_services, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry
* **Outbound deps:** runtime.tools.resources.ToolResources, runtime.tools.toolkit.RuntimeToolkit

### F145

* **Path:** `src/runtime/skills/__pycache__/registry.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F146

* **Path:** `src/runtime/skills/catalog/__pycache__/core_context.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F147

* **Path:** `src/runtime/skills/catalog/__pycache__/core_world.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F148

* **Path:** `src/runtime/skills/catalog/__pycache__/mcp_memory_read.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F149

* **Path:** `src/runtime/skills/catalog/__pycache__/mcp_memory_write.cpython-314.pyc`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).

### F150

* **Path:** `src/runtime/skills/catalog/core_context.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F151

* **Path:** `src/runtime/skills/catalog/core_world.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F152

* **Path:** `src/runtime/skills/catalog/mcp_memory_read.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F153

* **Path:** `src/runtime/skills/catalog/mcp_memory_write.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F154

* **Path:** `src/runtime/skills/registry.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F155

* **Path:** `src/runtime/state.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** controller.worker, resources/Documentation/Node_template.py, runtime.build, runtime.graph_build, runtime.langgraph_runner, runtime.nodes.llm_answer, runtime.nodes.llm_context_builder, runtime.nodes.llm_memory_retriever, runtime.nodes.llm_memory_writer, runtime.nodes.llm_reflect_topics, runtime.nodes.llm_router, runtime.nodes.llm_world_modifier, runtime.registry
* **Outbound deps:** none

### F156

* **Path:** `src/runtime/tool_loop.py`
* **Purpose:** Runtime orchestration utilities (graph, events, prompting, state).
* **Key symbols:** n/a
* **Inbound deps:** resources/Documentation/Node_template.py, runtime.nodes_common, runtime.tools.bindings.chat_history_tail, runtime.tools.bindings.memory_query, runtime.tools.bindings.memory_store, runtime.tools.providers.static_provider, runtime.tools.registry, runtime.tools.toolkit
* **Outbound deps:** runtime.deps._chat_params_from_mapping, runtime.emitter.TurnEmitter, runtime.providers.base.LLMProvider, runtime.providers.types.ChatRequest, runtime.providers.types.Message, runtime.providers.types.StreamEvent, runtime.providers.types.ToolCall, runtime.providers.types.ToolDef

### F157

* **Path:** `src/runtime/tools/__pycache__/registry.cpython-311.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F158

* **Path:** `src/runtime/tools/__pycache__/resources.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F159

* **Path:** `src/runtime/tools/__pycache__/toolkit.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F160

* **Path:** `src/runtime/tools/bindings/__pycache__/chat_history_tail.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F161

* **Path:** `src/runtime/tools/bindings/__pycache__/memory_query.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F162

* **Path:** `src/runtime/tools/bindings/__pycache__/memory_store.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F163

* **Path:** `src/runtime/tools/bindings/__pycache__/world_apply_ops.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F164

* **Path:** `src/runtime/tools/bindings/chat_history_tail.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.tool_loop.ToolHandler, runtime.tools.resources.ToolResources

### F165

* **Path:** `src/runtime/tools/bindings/memory_query.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.tool_loop.ToolHandler, runtime.tools.resources.ToolResources

### F166

* **Path:** `src/runtime/tools/bindings/memory_store.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.tool_loop.ToolHandler, runtime.tools.resources.ToolResources

### F167

* **Path:** `src/runtime/tools/bindings/world_apply_ops.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** controller.world_state.load_world_state, runtime.tools.resources.ToolResources

### F168

* **Path:** `src/runtime/tools/definitions/__pycache__/chat_history_tail.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F169

* **Path:** `src/runtime/tools/definitions/__pycache__/memory_query.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F170

* **Path:** `src/runtime/tools/definitions/__pycache__/memory_store.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F171

* **Path:** `src/runtime/tools/definitions/__pycache__/world_apply_ops.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F172

* **Path:** `src/runtime/tools/definitions/chat_history_tail.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.providers.types.ToolDef

### F173

* **Path:** `src/runtime/tools/definitions/memory_query.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.providers.types.ToolDef

### F174

* **Path:** `src/runtime/tools/definitions/memory_store.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.providers.types.ToolDef

### F175

* **Path:** `src/runtime/tools/definitions/world_apply_ops.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.providers.static_provider
* **Outbound deps:** runtime.providers.types.ToolDef

### F176

* **Path:** `src/runtime/tools/policy/__pycache__/node_skill_policy.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F177

* **Path:** `src/runtime/tools/policy/node_skill_policy.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** none

### F178

* **Path:** `src/runtime/tools/providers/__pycache__/static_provider.cpython-314.pyc`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).

### F179

* **Path:** `src/runtime/tools/providers/static_provider.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** runtime.tools.toolkit
* **Outbound deps:** runtime.providers.types.ToolDef, runtime.tool_loop.ToolHandler, runtime.tools.bindings.chat_history_tail, runtime.tools.bindings.memory_query, runtime.tools.bindings.memory_store, runtime.tools.bindings.world_apply_ops, runtime.tools.definitions.chat_history_tail, runtime.tools.definitions.memory_query, runtime.tools.definitions.memory_store, runtime.tools.definitions.world_apply_ops, runtime.tools.resources.ToolResources

### F180

* **Path:** `src/runtime/tools/registry.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** runtime.providers.types.ToolDef, runtime.tool_loop.ToolHandler, runtime.tool_loop.ToolSet

### F181

* **Path:** `src/runtime/tools/resources.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** controller.runtime_services, runtime.services, runtime.tools.bindings.chat_history_tail, runtime.tools.bindings.memory_query, runtime.tools.bindings.memory_store, runtime.tools.bindings.world_apply_ops, runtime.tools.providers.static_provider, runtime.tools.toolkit
* **Outbound deps:** none

### F182

* **Path:** `src/runtime/tools/toolkit.py`
* **Purpose:** Runtime tool system (definitions/bindings/policy/resources).
* **Key symbols:** n/a
* **Inbound deps:** controller.runtime_services, runtime.services
* **Outbound deps:** runtime.skills.catalog.core_context, runtime.skills.catalog.core_world, runtime.skills.catalog.mcp_memory_read, runtime.skills.catalog.mcp_memory_write, runtime.skills.registry.ENABLED_SKILLS, runtime.tool_loop.ToolSet, runtime.tools.policy.node_skill_policy.NODE_ALLOWED_SKILLS, runtime.tools.providers.static_provider.StaticProvider, runtime.tools.resources.ToolResources

### F183

* **Path:** `src/tests/__init__.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F184

* **Path:** `src/tests/__pycache__/__init__.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F185

* **Path:** `src/tests/__pycache__/__init__.cpython-314.pyc`
* **Purpose:** Developer test/probe scripts.

### F186

* **Path:** `src/tests/__pycache__/chat_history_smoketest.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F187

* **Path:** `src/tests/__pycache__/chat_history_smoketest.cpython-314.pyc`
* **Purpose:** Developer test/probe scripts.

### F188

* **Path:** `src/tests/__pycache__/langchain_probe_list_parsers.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F189

* **Path:** `src/tests/__pycache__/langchain_probe_output_parser.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F190

* **Path:** `src/tests/__pycache__/langchain_probe_prompt_template.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F191

* **Path:** `src/tests/__pycache__/langchain_probe_router_tool_selection.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F192

* **Path:** `src/tests/__pycache__/langchain_probe_text_splitter.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F193

* **Path:** `src/tests/__pycache__/langgraph_test.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F194

* **Path:** `src/tests/__pycache__/langgraph_test_ollama_router.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F195

* **Path:** `src/tests/__pycache__/langgraph_test_ollama_router_planner_answer.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F196

* **Path:** `src/tests/__pycache__/memory_k_selftest.cpython-314.pyc`
* **Purpose:** Developer test/probe scripts.

### F197

* **Path:** `src/tests/__pycache__/ollama_chat_interactive.cpython-311.pyc`
* **Purpose:** Developer test/probe scripts.

### F198

* **Path:** `src/tests/__pycache__/ollama_chat_interactive.cpython-314.pyc`
* **Purpose:** Developer test/probe scripts.

### F199

* **Path:** `src/tests/__pycache__/openmemory_interactive.cpython-314.pyc`
* **Purpose:** Developer test/probe scripts.

### F200

* **Path:** `src/tests/chat_history_smoketest.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F201

* **Path:** `src/tests/langchain_probe_list_parsers.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F202

* **Path:** `src/tests/langchain_probe_output_parser.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F203

* **Path:** `src/tests/langchain_probe_prompt_template.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F204

* **Path:** `src/tests/langchain_probe_router_tool_selection.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F205

* **Path:** `src/tests/langchain_probe_text_splitter.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F206

* **Path:** `src/tests/langgraph_test.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F207

* **Path:** `src/tests/langgraph_test_ollama_router.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F208

* **Path:** `src/tests/langgraph_test_ollama_router_planner_answer.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F209

* **Path:** `src/tests/ollama_chat_interactive.py`
* **Purpose:** Developer test/probe scripts.
* **Key symbols:** n/a
* **Inbound deps:** unknown/none (not determinable from static imports)
* **Outbound deps:** none

### F210

* **Path:** `src/tests/probe_toolcall.json`
* **Purpose:** Developer test/probe scripts.
* **Key contents:** {

### F211

* **Path:** `src/tests/probe_toolcall_jsonmode.json`
* **Purpose:** Developer test/probe scripts.
* **Key contents:** {

### F212

* **Path:** `src/tests/probe_toolresult.json`
* **Purpose:** Developer test/probe scripts.
* **Key contents:** {

### F213

* **Path:** `src/ui/__pycache__/chat_renderer.cpython-311.pyc`
* **Purpose:** Qt UI layer.

### F214

* **Path:** `src/ui/__pycache__/chat_renderer.cpython-314.pyc`
* **Purpose:** Qt UI layer.

### F215

* **Path:** `src/ui/__pycache__/config_dialog.cpython-311.pyc`
* **Purpose:** Qt UI layer.

### F216

* **Path:** `src/ui/__pycache__/config_dialog.cpython-314.pyc`
* **Purpose:** Qt UI layer.

### F217

* **Path:** `src/ui/__pycache__/main_window.cpython-311.pyc`
* **Purpose:** Qt UI layer.

### F218

* **Path:** `src/ui/__pycache__/main_window.cpython-314.pyc`
* **Purpose:** Qt UI layer.

### F219

* **Path:** `src/ui/__pycache__/widgets.cpython-311.pyc`
* **Purpose:** Qt UI layer.

### F220

* **Path:** `src/ui/__pycache__/widgets.cpython-314.pyc`
* **Purpose:** Qt UI layer.

### F221

* **Path:** `src/ui/chat_renderer.py`
* **Purpose:** Qt UI layer.
* **Key symbols:** n/a
* **Inbound deps:** ui.main_window
* **Outbound deps:** none

### F222

* **Path:** `src/ui/config_dialog.py`
* **Purpose:** Qt UI layer.
* **Key symbols:** n/a
* **Inbound deps:** ui.main_window
* **Outbound deps:** none

### F223

* **Path:** `src/ui/main_window.py`
* **Purpose:** Qt UI layer.
* **Key symbols:** n/a
* **Inbound deps:** llm_thalamus
* **Outbound deps:** ui.chat_renderer.ChatRenderer, ui.config_dialog.ConfigDialog, ui.widgets.BrainWidget, ui.widgets.ChatInput, ui.widgets.CombinedLogsWindow, ui.widgets.WorldSummaryWidget

### F224

* **Path:** `src/ui/widgets.py`
* **Purpose:** Qt UI layer.
* **Key symbols:** n/a
* **Inbound deps:** ui.main_window
* **Outbound deps:** none

### F225

* **Path:** `var/llm-thalamus-dev/data/chat_history.jsonl`
* **Purpose:** Dev runtime data/state (sample world_state, chat history).
* **Key contents:** {"ts": "2026-02-24T18:09:15+02:00", "role": "human", "content": "Try to fetch 10 memories about my family."}

### F226

* **Path:** `var/llm-thalamus-dev/state/world_state.json`
* **Purpose:** Dev runtime data/state (sample world_state, chat history).
* **Key contents:** {
