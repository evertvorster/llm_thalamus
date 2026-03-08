# llm_thalamus audit overview

## Index

- `audit_overview.md` — sections 0–9, 11–12
- `audit_file_inventory.md` — complete section 10 per-file inventory
- `audit_appendix.md` — supplementary notes, snapshot caveats, and extra diagrams

## 0) Document Control

**Snapshot identifier:** provided snapshot  
**Audit date:** 2026-03-08  
**Primary source:** uploaded archive `llm_thalamus-2026-03-08.zip`  
**Important caveat:** the tree pasted in the prompt listed hidden directories such as `.continue/` and `.vscode/`, but those directories were not present in the uploaded archive. This audit inventories the archive contents as the source of truth. Hidden-directory items from the pasted tree are called out only as missing-from-archive caveats.

### How to use this document

Use this document as the planning map for structural work. Start with sections 3 and 4 for runtime understanding, then section 11 for forward-fit analysis, and section 12 for incremental sequencing. Use `audit_file_inventory.md` when you need exact file references.

### Conventions used

- Paths are repo-relative and exact.
- Symbol names are exact where visible in code.
- “Inbound deps” means static importers or obvious direct callers found in code.
- “Unknown from snapshot” means the archive did not expose enough evidence.
- “World” means durable state intended to survive turns.
- “State” means the per-turn runtime `State` dict unless otherwise specified.

## 1) System Overview

### What the system does today

`llm_thalamus` is a local desktop chat application with a Qt UI and a small LangGraph runtime. A user message enters through the UI, is persisted to a JSONL history file, then flows through a 4-node runtime graph:

1. `context.bootstrap`
2. `llm.context_builder`
3. `llm.answer`
4. `llm.reflect`

The graph uses:
- prompt-based LLM nodes via an `LLMProvider` abstraction,
- a deterministic tool loop for tool-calling nodes,
- a durable `world_state.json`,
- a JSONL chat history file,
- optional OpenMemory access via MCP.

The runtime today is narrower than some bundled docs imply. There is no shipped router node, planner node, memory-writer node, or world-modifier node in the current graph. Those appear to be earlier or future design intent, not current behavior.

### Major subsystems

- **UI layer** — `src/ui/*`, `src/controller/worker.py`
- **Config/bootstrap** — `src/config/*`, `src/llm_thalamus.py`
- **Runtime/orchestrator** — `src/runtime/langgraph_runner.py`, `src/runtime/graph_build.py`, `src/runtime/nodes_common.py`
- **Nodes/graph** — `src/runtime/nodes/*`, `src/runtime/registry.py`
- **Tooling** — `src/runtime/tool_loop.py`, `src/runtime/tools/*`, `src/runtime/skills/*`
- **Persistence** — `src/controller/chat_history.py`, `src/controller/world_state.py`, `var/llm-thalamus-dev/*`
- **Provider abstraction** — `src/runtime/providers/*`
- **MCP client boundary** — `src/controller/mcp/*`

### High-level diagram

```text
src/llm_thalamus.py
  -> config.bootstrap_config()
  -> QApplication
  -> ControllerWorker(cfg)
       -> load_world_state()
       -> build_runtime_services()
  -> MainWindow(cfg, controller)

User sends message
  -> MainWindow._on_send_clicked()
  -> ControllerWorker.submit_message()
  -> ControllerWorker._handle_message()
       -> append_turn(human)
       -> build_runtime_deps(cfg)
       -> new_runtime_state(user_text)
       -> state["world"] = controller-owned world snapshot
       -> run_turn_runtime(state, deps, services)
            -> build_compiled_graph()
            -> install TurnEmitter in state["runtime"]["emitter"]
            -> LangGraph invoke:
                 context.bootstrap
                 -> llm.context_builder
                 -> llm.answer
                 -> llm.reflect
            -> stream TurnEvents back to worker
       -> append_turn(you)
       -> commit_world_state() on final world
  -> MainWindow updates chat / brain / logs / world panel
```

## 2) Repository Layout

### Top-level directories

#### `resources/`
Purpose:
- shipped runtime assets and documentation

Contents:
- `resources/config/config.json`
- prompt templates under `resources/prompts/`
- graphics under `resources/graphics/`
- bundled documentation under `resources/Documentation/`

Hotspots:
- `resources/config/config.json`
- `resources/prompts/runtime_*.txt`

Notes:
- Bundled audit docs are stale relative to the current runtime graph.
- Installed-mode graphics path is expected by code, but the Makefile comments claim graphics are not installed by this package.

#### `src/`
Purpose:
- all executable application code

Contents:
- config bootstrap code
- controller/UI code
- runtime graph, nodes, providers, tools
- tests and spike scripts

Hotspots:
- `src/controller/worker.py`
- `src/runtime/nodes_common.py`
- `src/runtime/tool_loop.py`
- `src/runtime/graph_build.py`
- `src/runtime/tools/bindings/world_apply_ops.py`
- `src/runtime/providers/ollama.py`
- `src/ui/main_window.py`

#### `var/llm-thalamus-dev/`
Purpose:
- repo-local dev runtime data

Contents:
- `data/chat_history.jsonl`
- `state/world_state.json`

Hotspots:
- not code hotspots, but important schema examples

### Top-level files

- `src/llm_thalamus.py` — executable module entrypoint
- `README.md`, `README_developer.md`, `CONTRIBUTING.md` — human docs
- `Makefile` — install/uninstall
- `llm_thalamus.desktop` — desktop entry

## 3) Runtime Walkthrough (end-to-end)

### 3.1 Entry point and initialization

1. `src/llm_thalamus.py:main(argv)` calls `config.bootstrap_config(argv)`.
2. `config.bootstrap_config()`:
   - parses `--dev` via `src/config/_cli.py`
   - locates project root via `src/config/_rootfind.py`
   - computes dev or installed paths via `src/config/_policy.py`
   - ensures installed-mode config file exists via `src/config/_load.py`
   - loads raw JSON config
   - derives a `ConfigSnapshot` via `src/config/_schema.py`
3. `src/llm_thalamus.py` prints a config summary.
4. It creates:
   - `QApplication`
   - `ControllerWorker(cfg)`
   - `MainWindow(cfg, controller)`

### 3.2 Controller setup

`src/controller/worker.py:ControllerWorker.__init__` does four important things:

1. Creates and starts a `QThread`.
2. Computes the authoritative world-state path.
3. Loads the durable world via `load_world_state(path=..., now_iso=...)`.
4. Builds runtime services via `build_runtime_services(...)`.

`src/controller/runtime_services.py:build_runtime_services(...)` wires:
- `FileChatHistoryService`
- optional `MCPClient`
- `ToolResources`
- `RuntimeToolkit`
- `RuntimeServices`

### 3.3 User turn startup

When the UI submits text:

1. `MainWindow` calls `ControllerWorker.submit_message(text)`.
2. `ControllerWorker.submit_message()` starts a background Python thread targeting `_handle_message(text)`.
3. `_handle_message()`:
   - appends the human turn to `chat_history.jsonl` using `append_turn(...)`
   - builds `Deps` with `build_runtime_deps(self._cfg)`
   - creates a fresh turn state with `new_runtime_state(user_text=text)`
   - copies the controller-owned world snapshot into `state["world"]`
   - calls `run_turn_runtime(state, deps, self._runtime_services)`

### 3.4 Dependency wiring

`src/runtime/deps.py:build_runtime_deps(cfg)`:

1. resolves prompt root from `cfg.resources_root / "prompts"`
2. creates a provider via `runtime.providers.factory.make_provider(...)`
3. validates all configured role models are installed by calling `provider.list_models()`
4. constructs:
   - `RoleSpec` per role
   - `RoleLLM` per role
   - `Deps(prompt_root, provider, roles, llms_by_role, tool_step_limit)`

Current required roles from config extraction are:
- `answer`
- `planner`
- `reflect`

Current graph usage is:
- `planner` role is used by `llm.context_builder`
- `answer` role is used by `llm.answer`
- `reflect` role is used by `llm.reflect`

### 3.5 Graph build and execution flow

`src/runtime/langgraph_runner.py:run_turn_runtime(...)`:

1. calls `build_compiled_graph(deps, services)`
2. ensures baseline keys exist in state
3. injects time fields from `services.tool_resources`
4. creates a `turn_id` if absent
5. creates:
   - `TurnEventFactory`
   - `EventBus`
   - `TurnEmitter`
6. stores the emitter into `state["runtime"]["emitter"]`
7. emits `turn_start`
8. runs `compiled.invoke(state)` on a background thread
9. yields TurnEvents from `EventBus.events_live(...)`
10. after graph completion, emits:
   - `world_commit`
   - `turn_end`

### 3.6 Node sequence

`src/runtime/graph_build.py:build_compiled_graph(...)` defines:

```text
entry -> context_bootstrap -> context_builder -> answer -> reflect -> END
```

Detailed behavior:

- `context_bootstrap`
  - mechanical tool prefill only
  - no prompt
- `context_builder`
  - LLM controller node with tools
  - writes `context.next`
- conditional edge
  - currently maps everything to `"answer"`
  - `"planner"` is recognized in prompt text but not graph-wired
- `answer`
  - simple streaming answer node
  - no tools
- `reflect`
  - LLM controller node with tools
  - updates topics and stores memories

### 3.7 Context building and prompt construction

Prompt rendering is centralized in `src/runtime/nodes_common.py`:

- `TokenBuilder` loads the prompt via `deps.load_prompt(prompt_name)`
- tokens are discovered in the prompt via regex `<<TOKEN>>`
- token values are resolved from `GLOBAL_TOKEN_SPEC`
- `runtime.prompting.render_tokens(...)` replaces tokens and errors if any placeholders remain

Current prompt files:
- `resources/prompts/runtime_context_builder.txt`
- `resources/prompts/runtime_answer.txt`
- `resources/prompts/runtime_reflect.txt`

### 3.8 Tool loop behavior

Controller nodes use `run_controller_node(...)` in `src/runtime/nodes_common.py`, which delegates to `src/runtime/tool_loop.py:chat_stream(...)`.

Tool loop behavior:

1. build `ChatRequest` with tools enabled and `response_format=None`
2. stream provider output and collect tool calls
3. if tool calls appear:
   - validate arguments JSON
   - execute bound tool handlers deterministically
   - append tool results as `Message(role="tool", ...)`
   - continue to next step
4. if no tool calls appear:
   - if a `response_format` is required, run one final tools-disabled formatting pass
   - otherwise finish

Important boundary:
- nodes do not execute tools directly during normal controller rounds
- tool definitions and bindings are assembled per node by `RuntimeToolkit.toolset_for_node(node_key)`

Exception:
- `context.bootstrap` uses `run_tools_mechanically(...)`, a deterministic prefill path with no LLM tool-call round.

### 3.9 Persistence updates

#### Chat history
- written by `ControllerWorker._handle_message()` before and after the turn
- stored at `cfg.message_file`
- schema: one JSON object per line with `ts`, `role`, `content`

#### World state
- loaded once into `ControllerWorker._world`
- copied into turn state at start of turn
- may be replaced in turn state by tool results from `world_apply_ops`
- finally committed by `ControllerWorker` after `world_commit`

#### Memory
- accessed only via MCP-backed tools:
  - `memory_query`
  - `memory_store`

### 3.10 UI/logging event handling

The worker consumes `TurnEvent` objects and maps them to Qt signals:
- node lifecycle -> thinking panel updates
- `llm_request` -> prompt capture panel
- assistant stream events -> streaming chat bubble
- `world_update` -> live world debug panel
- `state_update` -> live state debug panel
- `log_line` -> combined log window

### Textual sequence diagram

```text
UI -> ControllerWorker.submit_message
ControllerWorker -> chat_history.append_turn(human)
ControllerWorker -> build_runtime_deps
ControllerWorker -> new_runtime_state
ControllerWorker -> run_turn_runtime
run_turn_runtime -> TurnEmitter.start_turn
run_turn_runtime -> LangGraph.invoke
LangGraph -> context.bootstrap
context.bootstrap -> chat_history_tail
context.bootstrap -> memory_query? (topic-derived)
LangGraph -> llm.context_builder
llm.context_builder -> tool_loop.chat_stream
tool_loop -> provider.chat_stream
tool_loop -> bound tool handlers
llm.context_builder -> updates state.context / maybe state.world
LangGraph -> llm.answer
llm.answer -> provider.chat_stream
llm.answer -> assistant_start/delta/end events
LangGraph -> llm.reflect
llm.reflect -> tool_loop.chat_stream
tool_loop -> world_apply_ops / memory_store
llm.reflect -> updates state.world / runtime.reflect_result
run_turn_runtime -> world_commit
ControllerWorker -> chat_history.append_turn(you)
ControllerWorker -> commit_world_state
ControllerWorker -> UI signals
```

## 4) State and Dataflow Model (core of the report)

### 4.1 Durable world state vs per-turn working state

#### Durable world state
Location:
- `var/llm-thalamus-dev/state/world_state.json` in dev mode
- installed-mode equivalent under `cfg.state_root`

Managed by:
- `src/controller/world_state.py`
- `src/controller/worker.py`

Observed schema in code:
- `updated_at: str`
- `project: str`
- `topics: list[str]`
- `goals: list`
- `rules: list`
- `identity: { user_name, session_user_name, agent_name, user_location }`
- optional `tz: str`

#### Per-turn working state
Created by:
- `src/runtime/state.py:new_runtime_state(user_text=...)`

Mutated by:
- runtime runner
- bootstrap node
- controller nodes
- answer node
- reflect node

Transport:
- passed as a mutable dict through LangGraph
- also read by the UI through sanitized `state_update` snapshots

### 4.2 State structures

#### `state["task"]`
Created:
- `new_runtime_state()`

Read by:
- prompt token resolution (`USER_MESSAGE`)
- `run_turn_runtime` for `turn_start`
- answer/context/reflect prompts

Mutated by:
- not meaningfully mutated in current graph

Observed fields:
- `user_text: str`
- `language: str` (default `"en"`)

#### `state["runtime"]`
Created:
- `new_runtime_state()`
- expanded in `run_turn_runtime(...)`
- expanded further by nodes

Read by:
- prompts (`NOW_ISO`, `TIMEZONE`, `STATUS`, `ISSUES_JSON`)
- UI via `state_update`
- nodes via shared helpers

Mutated by:
- `run_turn_runtime`
- `append_node_trace`
- `context_bootstrap`
- `llm_context_builder.apply_handoff`
- `llm_reflect.apply_handoff`

Observed fields from code:
- base from `new_runtime_state`:
  - `node_trace: list[str]`
  - `status: str`
  - `issues: list[str]`
  - `now_iso: str`
  - `timezone: str`
- added by runner:
  - `timestamp: int` (best effort)
  - `turn_id: str`
  - `emitter: TurnEmitter`
- added by `context.bootstrap`:
  - `context_bootstrap_status`
  - `context_bootstrap_seeded`
- added by `llm.context_builder`:
  - `context_builder_complete`
  - `context_builder_next`
  - `context_builder_status`
- added by `llm.reflect`:
  - `reflect_complete`
  - `reflect_status`
  - `reflect_stored_count`
  - `reflect_result`

Pain point:
- `RuntimeRuntime` TypedDict in `src/runtime/state.py` is much narrower than actual runtime usage.

#### `state["context"]`
Created:
- `new_runtime_state()` as `{}`
- normalized in bootstrap/context_builder/reflect nodes

Read by:
- prompt token `CONTEXT_JSON`
- graph conditional selector in `graph_build.py`
- answer node prompt

Mutated by:
- `context.bootstrap`
- `llm.context_builder`
- `llm.reflect`

Observed fields:
- `sources: list[dict]`
- `complete: bool`
- `next: str`
- `issues: list[str]`
- `notes: str`
- possibly `next_node`, `route`, `memory_request.k` (prompt token spec anticipates these)
- context-source entries with shapes like:
  - `{kind, title, records, meta}`

Pain point:
- tool-return normalization is inconsistent:
  - `chat_history_tail` source stores `records = payload["items"]`
  - `memory_query` in bootstrap stores the whole payload wrapper
  - `memory_query` in context_builder stores `payload`
  - names alternate between `items` and `records`

#### `state["final"]`
Created:
- `new_runtime_state()`

Read by:
- reflect prompt tokens (`ASSISTANT_ANSWER`)
- UI state snapshots

Mutated by:
- `llm.answer` writes `state["final"]["answer"]`

Observed fields:
- `answer: str`

#### `state["world"]`
Created:
- copied from controller-owned world into turn state before runtime starts

Read by:
- bootstrap topic query
- all prompt tokens using `WORLD_JSON`
- graph end lifecycle in runner
- UI state snapshot

Mutated by:
- `llm.context_builder.apply_tool_result()` when `world_apply_ops` returns a world object
- `llm.reflect.apply_tool_result()` similarly

Critical pain point:
- `world_apply_ops` binding reloads world from disk for each call instead of starting from the current in-turn `state["world"]`.
- Because the controller commits only after the turn ends, a second `world_apply_ops` call in the same turn can start from stale disk state and overwrite earlier same-turn in-memory changes.

#### Private scratch keys
Observed:
- `_reflect_stored_count`

Used by:
- `llm.reflect` to count successful `memory_store` calls across rounds

### 4.3 Durable world state lifecycle

1. worker loads disk state into `self._world`
2. new turn copies `self._world` into `state["world"]`
3. nodes may replace `state["world"]` with tool-returned variants
4. `run_turn_runtime` emits `world_commit`
5. worker commits `final_world` back to disk
6. worker refreshes UI world panel

### 4.4 Current pain points affecting future direction

#### Scoped state views
Current blockers:
- state is a single mutable dict shared by all nodes
- TypedDict contracts are incomplete
- prompts receive broad JSON blobs (`WORLD_JSON`, `CONTEXT_JSON`) rather than projected views
- evidence packets are not uniform

#### `project_status`
Current blockers:
- there is no deterministic manifest compiler or mechanical status snapshot
- world state contains free-form lists but no formal project-status substructure
- prompt files currently see the entire world/context blobs rather than a compiled status artifact

#### Tool contract boundaries
Strength:
- nodes do not import MCP classes directly

Blockers:
- bindings still know exact OpenMemory tool names
- `world_apply_ops` is named like a persistence action but is actually “load-disk-world, mutate in memory, return object”
- mechanical bootstrap path bypasses the normal controller node loop, so capability behavior is split across two execution patterns

## 5) Subsystem Deep Dives

### 5.1 UI layer

Responsibilities:
- render chat
- collect user input
- show world summary
- show debug logs, thinking stream, prompt payloads
- manage busy/brain animation state

Key modules:
- `src/ui/main_window.py`
- `src/ui/chat_renderer.py`
- `src/ui/widgets.py`
- `src/ui/config_dialog.py`

Public interfaces:
- `MainWindow(cfg, controller)`
- `ChatRenderer.add_turn(...)`, streaming methods
- `BrainWidget`, `WorldSummaryWidget`, `CombinedLogsWindow`
- `ConfigDialog`

Dependencies:
- depends on `ControllerWorker` signal names and semantics
- uses `cfg.graphics_dir`
- reads `world_state.json` path via controller API

Hotspots:
- `MainWindow` is the main UI composition/wiring hotspot
- `widgets.py` groups many unrelated widgets into one file
- `config_dialog.py` is large and schema-sensitive

### 5.2 Runtime / orchestrator layer

Responsibilities:
- build runtime deps
- build graph
- run graph with streaming events
- manage turn event protocol

Key modules:
- `src/runtime/deps.py`
- `src/runtime/graph_build.py`
- `src/runtime/langgraph_runner.py`
- `src/runtime/events.py`
- `src/runtime/emitter.py`
- `src/runtime/event_bus.py`
- `src/runtime/state.py`

Public interfaces:
- `build_runtime_deps(cfg)`
- `build_compiled_graph(deps, services)`
- `run_turn_runtime(state, deps, services)`

Dependencies:
- provider subsystem
- node registry
- runtime services/toolkit
- controller worker

Hotspots:
- `langgraph_runner.py`
- `nodes_common.py` because it contains shared execution logic

### 5.3 Graph / nodes layer

Responsibilities:
- implement the four runtime stages
- own node-local prompt/tool/state contracts

Key modules:
- `src/runtime/nodes/context_bootstrap.py`
- `src/runtime/nodes/llm_context_builder.py`
- `src/runtime/nodes/llm_answer.py`
- `src/runtime/nodes/llm_reflect.py`
- `src/runtime/nodes_common.py`
- `src/runtime/registry.py`

Public interfaces:
- each node module exports `make(deps, services)` and self-registers a `NodeSpec`

Dependencies:
- prompts via `deps.load_prompt`
- tools via `RuntimeServices.tools.toolset_for_node`
- event emitter via `state["runtime"]["emitter"]`

Hotspots:
- `nodes_common.py`
- `llm_context_builder.py`
- `llm_reflect.py`

### 5.4 Tooling layer

Responsibilities:
- define tool schemas
- bind implementations to resources
- gate skills by node
- execute tool loop

Key modules:
- `src/runtime/tool_loop.py`
- `src/runtime/tools/toolkit.py`
- `src/runtime/tools/providers/static_provider.py`
- `src/runtime/tools/policy/node_skill_policy.py`
- `src/runtime/tools/definitions/*`
- `src/runtime/tools/bindings/*`
- `src/runtime/skills/*`

Public interfaces:
- `RuntimeToolkit.toolset_for_node(node_key)`
- `chat_stream(...)` tool loop
- individual `tool_def()` and `bind(resources)` functions

Dependencies:
- provider types
- ToolResources
- MCP client through ToolResources only

Hotspots:
- `tool_loop.py`
- `world_apply_ops` binding
- `StaticProvider.get(name)`

### 5.5 Prompt / resources layer

Responsibilities:
- store shipped prompts and config template
- define placeholder contract

Key modules/files:
- `resources/prompts/runtime_context_builder.txt`
- `resources/prompts/runtime_answer.txt`
- `resources/prompts/runtime_reflect.txt`
- `src/runtime/prompting.py`
- `src/runtime/nodes_common.py` (`GLOBAL_TOKEN_SPEC`, `TokenBuilder`)
- `resources/config/config.json`

Dependencies:
- all prompt-driven nodes
- config bootstrap
- UI graphics loading

Coupling/hotspots:
- prompt placeholders are centrally defined in code, so any new prompt token requires editing `GLOBAL_TOKEN_SPEC`
- shipped docs under `resources/Documentation/` are not aligned with current code

### 5.6 Persistence / data layer

Responsibilities:
- JSONL chat history
- JSON world state
- MCP-backed memory calls

Key modules:
- `src/controller/chat_history.py`
- `src/controller/chat_history_service.py`
- `src/controller/world_state.py`
- `src/controller/mcp/client.py`
- `src/controller/mcp/transport_streamable_http.py`

Dependencies:
- controller worker
- tool bindings
- runtime services construction

Hotspots:
- `world_state.py` + `world_apply_ops` binding boundary
- MCP client semantics vs tool contract stability

### 5.7 Supporting utilities / scripts

Responsibilities:
- packaging
- spike/probe scripts
- bundled docs/templates

Key modules/files:
- `Makefile`
- `llm_thalamus.desktop`
- `src/tests/*`
- `resources/Documentation/*`

Notes:
- many `src/tests/*` are probes/spikes, not integrated tests
- several docs/scripts target older architecture names

### 5.8 Tests and dev tooling

Current state:
- mostly manual probes and prototypes
- little evidence of assertions against the current shipped graph
- some tests are clearly stale (`chat_history_smoketest.py` import path mismatch)

Implication:
- architectural regression detection is currently weak

## 6) Node Catalog

### `context.bootstrap`
File:
- `src/runtime/nodes/context_bootstrap.py`

Registered as:
- `node_id="context.bootstrap"`

Purpose:
- seed `context.sources` mechanically before any LLM routing/classification work

Expected inputs:
- `state["world"]`
- `state["runtime"]["emitter"]`

Outputs:
- updates `state["context"]["sources"]`
- sets:
  - `runtime.context_bootstrap_status`
  - `runtime.context_bootstrap_seeded`

Prompt:
- none

Tool access policy:
- node key passed to toolkit: `"context_bootstrap"`
- allowed skills:
  - `core_context`
  - `mcp_memory_read`

Concrete tools reachable:
- `chat_history_tail`
- `memory_query`

Graph placement:
- entry node
- always precedes `context_builder`

### `llm.context_builder`
File:
- `src/runtime/nodes/llm_context_builder.py`

Registered as:
- `node_id="llm.context_builder"`

Purpose:
- classify sufficiency, gather more evidence, optionally mutate world, and choose the next step

Expected inputs:
- `task.user_text`
- `world`
- `context`
- runtime emitter/time fields

Outputs:
- may update `context.sources`
- may update `context.issues`, `context.notes`
- sets `context.complete`
- sets `context.next`
- may replace `state["world"]`
- sets runtime context-builder status fields

Prompt:
- `resources/prompts/runtime_context_builder.txt`

Tool access policy:
- node key `"context_builder"`
- allowed skills:
  - `core_context`
  - `mcp_memory_read`
  - `core_world`

Concrete tools:
- `chat_history_tail`
- `memory_query`
- `world_apply_ops`

Graph placement:
- after `context.bootstrap`
- before conditional edge to `answer`

### `llm.answer`
File:
- `src/runtime/nodes/llm_answer.py`

Registered as:
- `node_id="llm.answer"`

Purpose:
- produce the user-facing response

Expected inputs:
- `task.user_text`
- `world`
- `context`
- runtime time/status/issues

Outputs:
- `final.answer`
- assistant stream events

Prompt:
- `resources/prompts/runtime_answer.txt`

Tool access policy:
- none

Graph placement:
- after `context_builder`
- before `reflect`

### `llm.reflect`
File:
- `src/runtime/nodes/llm_reflect.py`

Registered as:
- `node_id="llm.reflect"`

Purpose:
- post-answer persistence curation:
  - maintain `WORLD.topics`
  - store durable memories

Expected inputs:
- `task.user_text`
- `final.answer`
- `world`
- `context`

Outputs:
- may replace `state["world"]`
- writes runtime reflection summary fields
- uses private `_reflect_stored_count`

Prompt:
- `resources/prompts/runtime_reflect.txt`

Tool access policy:
- node key `"reflect"`
- allowed skills:
  - `core_world`
  - `mcp_memory_write`

Concrete tools:
- `world_apply_ops`
- `memory_store`

Graph placement:
- after `answer`
- terminal node before `END`

## 7) Tooling System Catalog

### 7.1 Tool registry / discovery

There is no dynamic discovery. Tool exposure is assembled in layers:

1. skill catalog under `src/runtime/skills/catalog/*.py`
2. enabled-skill registry in `src/runtime/skills/registry.py`
3. node skill policy in `src/runtime/tools/policy/node_skill_policy.py`
4. static provider in `src/runtime/tools/providers/static_provider.py`
5. runtime toolkit in `src/runtime/tools/toolkit.py`

This is explicit and predictable. It also means every new skill/tool path requires code edits in several places.

### 7.2 Tool loop

Implemented in:
- `src/runtime/tool_loop.py:chat_stream(...)`

Core contract:
- while tools are available:
  - do not force `response_format`
- once no more tool calls appear:
  - optionally run a final tools-disabled formatting pass

Validation points:
- tool names must exist in `ToolSet.handlers`
- args must parse as JSON object
- optional validators may run on handler output

Error handling:
- handler exceptions become synthetic JSON tool results:
  - `{"ok": false, "error": ...}`
- the node/turn is not aborted immediately

### 7.3 Tool result formatting and reinjection

Formatting:
- `_normalize_tool_result(...)`
  - strings pass through
  - non-strings are `json.dumps(...)`

Re-entry path:
- tool results are appended as `Message(role="tool", name=..., tool_call_id=..., content=result_text)`

### 7.4 Logging

What is logged:
- tool call arguments
- tool errors
- final LLM output for controller nodes
- LLM provider payloads via `llm_request`
- node start/end
- thinking deltas
- assistant stream deltas
- world/state update snapshots

Where it goes:
- runtime emits `TurnEvent`
- `ControllerWorker` converts these into Qt signals
- `MainWindow`/log widgets display or buffer them

Missing/weak:
- no durable structured execution ledger
- `world_commit` delta can be wrong due to mutable-state timing

### 7.5 Existing MCP client usage and boundaries

Current MCP boundary is good at the node layer:
- nodes do not import MCP client code directly
- MCP is instantiated in `src/controller/runtime_services.py`
- MCP is carried via `ToolResources.mcp`
- only tool bindings call `resources.mcp.call_tool(...)`

Bindings still hard-code OpenMemory tool names, which is acceptable but not yet provider-agnostic below the binding layer.

## 8) Persistence Catalog

### 8.1 `world_state.json`

Code:
- `src/controller/world_state.py`

Load behavior:
- create defaults if missing
- reset to defaults if corrupted
- refresh `updated_at` on load if `now_iso` is supplied
- add `tz` if missing and provided

Commit behavior:
- write to `*.tmp`
- replace target path

Important caveat:
- `world_apply_ops` does not itself commit to disk.

### 8.2 Memory / episodes DBs

Current snapshot evidence:
- there is no SQLite memory DB implementation visible in shipped code
- memory access is through MCP only

Any SQLite memory/episode design mentioned in docs is not current code.

### 8.3 Caches, indexes, logs, file stores

Visible caches:
- MCP client caches `tools/list` results in memory
- UI `BrainWidget` caches saturation-transformed pixmaps
- controller keeps `_world` in memory

Visible file stores:
- JSONL chat history
- JSON world state
- config JSON
- prompts/resources

Visible logs:
- runtime events are transient unless manually saved from the UI

### 8.4 Backup / consistency considerations

Strengths:
- world-state commit is atomic-ish
- chat history trimming rewrites via temp file

Risks:
- multiple same-turn world updates can lose intermediate changes because `world_apply_ops` reloads from disk each call
- `world_commit` delta reporting is unreliable
- no durable append-only turn ledger exists

## 9) Dependency & Call Graph Summaries

### 9.1 Package/module dependency overview

```text
config -> entrypoint
entrypoint -> controller + ui
controller -> runtime + persistence + mcp
runtime -> providers + tools + skills + nodes
nodes -> nodes_common + registry + runtime services
tools -> ToolResources -> controller services / MCP
ui -> controller signals
```

### 9.2 Key call chains

#### Startup
`src/llm_thalamus.py:main`
-> `config.bootstrap_config`
-> `ControllerWorker.__init__`
-> `build_runtime_services`
-> `MainWindow.__init__`

#### Turn execution
`ControllerWorker._handle_message`
-> `append_turn`
-> `build_runtime_deps`
-> `new_runtime_state`
-> `run_turn_runtime`
-> `build_compiled_graph`
-> node sequence
-> `commit_world_state`

#### Context-builder controller round
`llm_context_builder.make(...).node`
-> `nodes_common.run_controller_node`
-> `toolkit.toolset_for_node("context_builder")`
-> `tool_loop.chat_stream`
-> `provider.chat_stream`
-> bound tool handlers
-> `llm_context_builder.apply_tool_result`
-> `llm_context_builder.apply_handoff`

#### Reflection controller round
`llm_reflect.make(...).node`
-> `nodes_common.run_controller_node`
-> `toolkit.toolset_for_node("reflect")`
-> `tool_loop.chat_stream`
-> `memory_store` / `world_apply_ops`
-> `llm_reflect.apply_tool_result`
-> `llm_reflect.apply_handoff`

### 9.3 Change amplifiers

1. `src/controller/worker.py`
2. `src/runtime/nodes_common.py`
3. `src/runtime/tool_loop.py`
4. `src/runtime/tools/bindings/world_apply_ops.py`
5. `src/runtime/deps.py`
6. `src/ui/main_window.py`

## 11) Strategic Fit Check (forward plan alignment)

### Obsidian document store via MCP

Current fit:
- good at the node boundary
- nodes already consume tools through skill-gated tool contracts
- MCP is already hidden behind `ToolResources` and bindings

Best insertion points:
- add tool definitions/bindings under `src/runtime/tools/definitions/` and `src/runtime/tools/bindings/`
- register them in `src/runtime/tools/providers/static_provider.py`
- expose them through new skills under `src/runtime/skills/catalog/`
- allow them per node in `src/runtime/tools/policy/node_skill_policy.py`

Risk:
- current `context.sources` structure should be standardized first.

### MCP isolated behind tool contracts; nodes never call MCP directly

Current fit:
- mostly achieved

Needed refactoring:
- optional improvement: add an adapter layer so bindings do not hard-code exact OpenMemory MCP tool names

### Deterministic `project_status` manifest compiled mechanically

Current fit:
- not present

Best insertion points:
- new mechanical step in `context.bootstrap` or a new dedicated mechanical node
- likely a new token such as `PROJECT_STATUS_JSON` consumed by downstream prompts

### Scoped state views / per-node projections

Current fit:
- poor but tractable

Best insertion points:
- `src/runtime/nodes_common.py:TokenBuilder`
- `src/runtime/registry.py:NodeSpec` if extended with declared read/write keys

### Future episodic SQLite ledger (shelved, contract-driven)

Current fit:
- not implemented
- should be introduced behind tool contracts, not direct node/store imports

## 12) Recommendations (incremental)

1. Fix same-turn world mutation semantics in `src/runtime/tools/bindings/world_apply_ops.py`.
2. Capture a true pre-turn world snapshot in `src/runtime/langgraph_runner.py` before graph execution.
3. Standardize `context.sources` into one evidence-packet schema.
4. Expand `src/runtime/state.py` to match actual runtime fields.
5. Wire or remove the planner route explicitly.
6. Introduce a deterministic `project_status` compile step.
7. Add Obsidian via tool contracts, not direct node calls.
8. Fix the chat-history role mismatch in `src/runtime/tools/bindings/chat_history_tail.py`.
9. Refresh or remove stale bundled docs.
10. Install graphics in the package or stop referencing installed graphics paths.
11. Remove or clearly mark dead/unused modules (`graph_policy.py`, `prompt_loader.py`, probably `build.py`).
12. Add a durable turn ledger or structured runtime log sink.
13. Split `nodes_common.py` once contracts stabilize.
14. Split `ui/widgets.py` and likely `ui/main_window.py` by responsibility.
15. Prefer prompt-only adjustments for context-builder and reflect behavior before adding code paths where feasible.
16. Make node read/write contracts explicit in `NodeSpec`.
