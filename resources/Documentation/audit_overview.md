# LLM Thalamus – Architecture & Codebase Audit (Overview)

## Index
- This file: `audit_overview.md` (sections 0–9, 11–12)
- File inventory: `audit_file_inventory.md` (section 10)
- Appendix: `audit_appendix.md` (supporting tables)

## 0) Document Control
- **Snapshot identifier:** provided snapshot (zip sha1 `07fac4d1244980a0373c2e074aab68c029b1a38f`)
- **Date:** 2026-03-07
- **How to use this document:** Read sections 1–4 first. Use section 6 for node-level planning, section 7 for tool-boundary work, section 8 for persistence work, and section 10 for file-by-file impact analysis.
- **Conventions used in this report:**
  - Paths are repo-relative.
  - “State” means the per-turn dict flowing through LangGraph (`src/runtime/state.py`).
  - “World” means durable JSON persisted by `src/controller/world_state.py`.
  - Inventory references use file IDs like `F057`.

## 1) System Overview
### What the system does today
`llm_thalamus` is a local-first desktop chat application built around a LangGraph turn pipeline, a provider abstraction for LLM backends, a deterministic tool loop, and two persistent stores that are actually implemented in this snapshot: JSONL chat history and JSON world state. The UI is PySide6-based. Long-term memory is not a local SQLite store in this snapshot; instead it is reached through an MCP OpenMemory client exposed only via tool bindings.

### Major subsystems
- **UI:** `src/ui/*` plus `src/controller/worker.py`
- **Runtime / orchestration:** `src/runtime/*`
- **Graph / nodes:** `src/runtime/graph_build.py`, `src/runtime/nodes/*`
- **Tooling:** `src/runtime/tool_loop.py`, `src/runtime/tools/*`, `src/runtime/skills/*`
- **Persistence:** `src/controller/chat_history.py`, `src/controller/world_state.py`, sample data in `var/`
- **Resources:** `resources/prompts/*`, `resources/config/config.json`, `resources/graphics/*`

### High-level diagram
```text
PySide6 UI
  │
  ▼
ControllerWorker
  ├─ append human turn -> chat_history.jsonl
  ├─ build Deps (provider + role config + prompts)
  ├─ build RuntimeServices (tool resources + MCP client + toolkit)
  └─ run_turn_runtime(State, Deps, RuntimeServices)
         │
         ▼
     LangGraph
       router
         ├─ answer
         ├─ context_builder <-> memory_retriever
         └─ world_modifier
             ↓
           answer
             ↓
       reflect_topics
             ↓
       memory_writer
             ↓
            END
         │
         └─ central streaming tool loop
                provider chat round(s)
                -> deterministic handler execution
                -> tool message reinjection
```

## 2) Repository Layout
### `src/`
Purpose: application code.

Hotspots:
- `F039` `src/controller/worker.py`
- `F051` `src/runtime/nodes_common.py`
- `F057` `src/runtime/tool_loop.py`
- `F047` `src/runtime/graph_build.py`

### `resources/`
Purpose: prompts, config template, graphics, and documentation artifacts.

Notable hotspots:
- prompt contracts in `resources/prompts/*.txt`
- config template `F018`

### `var/`
Purpose: development-time sample state/history.

Contains:
- `var/llm-thalamus-dev/data/chat_history.jsonl`
- `var/llm-thalamus-dev/state/world_state.json`

### Top-level files
- `F011` `src/llm_thalamus.py`: real application entrypoint
- `F003` `Makefile`: installer
- `F004` / `F005`: architectural intent, but partly stale

### Snapshot discrepancy
The user-provided tree listed `.continue/` and `.vscode/`. Those paths are **not present in the provided zip**, so any analysis of those directories is unknown from snapshot.

## 3) Runtime Walkthrough (end-to-end)
### 3.1 Entry point(s) and initialization
1. `src/llm_thalamus.py:main(argv)` calls `config.bootstrap_config(argv)`.
2. It prints a config summary, creates `QApplication`, constructs `ControllerWorker(cfg)`, then `MainWindow(cfg, controller)`.
3. `ControllerWorker.__init__()`:
   - resolves history/world paths,
   - loads current world via `controller.world_state.load_world_state()`,
   - builds `RuntimeServices` using `controller.runtime_services.build_runtime_services()`.

### 3.2 Config loading and dependency wiring
Config flow:
1. `config.parse_bootstrap_args()` reads `--dev` and `LLM_THALAMUS_DEV`.
2. `config.find_project_root()` locates repo root by `resources/config/config.json`.
3. `config.compute_roots_for_mode()` resolves resource/config/data/state roots.
4. `config.load_raw_config_json()` loads JSON.
5. `config.extract_effective_values()` validates/normalizes effective settings.
6. At turn time, `runtime.deps.build_runtime_deps(cfg)`:
   - picks provider,
   - validates required model names exist,
   - builds `RoleSpec` / `RoleLLM` per role,
   - exposes `Deps.load_prompt()`.

### 3.3 Graph build and node sequence
Current runtime graph is built in `src/runtime/graph_build.py:build_compiled_graph(deps, services)`.

Actual flow:
1. `router`
2. conditional:
   - `context_builder`
   - `world_modifier`
   - `answer`
3. `context_builder` can loop to `memory_retriever` and back
4. `world_modifier -> answer`
5. `answer -> reflect_topics -> memory_writer -> END`

Notable detail: `src/runtime/build.py` still contains an older `router -> answer` bootstrap graph, but the UI runtime uses `src/runtime/langgraph_runner.py`, which imports `src/runtime/graph_build.py`.

### 3.4 Context building and prompt construction
Prompt loading/rendering is split across:
- `Deps.load_prompt()` in `src/runtime/deps.py`
- `render_tokens()` in `src/runtime/prompting.py`
- `TokenBuilder` in `src/runtime/nodes_common.py`

Prompt selection is per-node constant, for example:
- router -> `runtime_router`
- answer -> `runtime_answer`
- context builder -> `runtime_context_builder`

TokenBuilder resolves placeholders against a single `GLOBAL_TOKEN_SPEC`. That is the current prompt contract backbone.

### 3.5 Tool loop behavior and how tool results re-enter the model
Central logic: `src/runtime/tool_loop.py:chat_stream()`.

Behavior:
1. If tools are disabled for a call, do one provider streaming pass.
2. If tools are enabled:
   - run a provider round with tool schemas and `response_format=None`,
   - collect tool calls,
   - execute tool handlers deterministically,
   - append `Message(role="tool", ...)` entries to `messages`,
   - repeat until no more tool calls or `max_steps` exceeded,
   - if the node expects structured JSON, do one final formatting pass with tools disabled and `response_format` re-enabled.

This is a strong architectural seam: nodes do not directly execute MCP or persistence logic during the LLM conversation. They call `chat_stream()`, which owns the tool contract.

There is one additional path: `nodes_common.run_tools_mechanically()` lets a node execute tool handlers *without* an LLM tool call. Today that is used by `llm.router` for mechanical prefill.

### 3.6 Persistence updates
Implemented persistence in snapshot:
- **Chat history:** JSONL file written by `controller.chat_history.append_turn()`
- **World state:** JSON file loaded/committed by `controller.world_state.*`
- **OpenMemory:** only through MCP tool handlers `memory_query` and `memory_store`

Not implemented in code snapshot despite documentation references:
- local `memory.sqlite`
- local `episodes.sqlite`
- deterministic `project_status` manifest

### 3.7 UI/logging events
`src/runtime/langgraph_runner.py` installs a `TurnEmitter` into `state["runtime"]["emitter"]` and yields `TurnEvent` dicts through `EventBus`.
`ControllerWorker._handle_message()` consumes these events and fans them out into Qt signals for:
- streamed assistant text
- thinking text
- prompt capture (`llm_request`)
- log lines
- state snapshots
- world snapshots/commits

### 3.8 Numbered sequence diagram
```text
1. MainWindow -> ControllerWorker.submit_message(text)
2. ControllerWorker._handle_message():
   2.1 append user turn to JSONL
   2.2 deps = build_runtime_deps(cfg)
   2.3 state = new_runtime_state(user_text=text)
   2.4 state["world"] = controller-owned world snapshot
   2.5 iterate run_turn_runtime(state, deps, runtime_services)
3. run_turn_runtime():
   3.1 build compiled graph
   3.2 install emitter into state["runtime"]
   3.3 emit turn_start
   3.4 invoke graph in background thread
   3.5 stream EventBus events live
4. Node execution:
   4.1 node helper renders prompt
   4.2 node helper calls tool_loop.chat_stream(...)
   4.3 provider streams deltas/tool_calls
   4.4 tool loop executes handlers and appends tool results
   4.5 node applies final structured result back into state
5. After graph:
   5.1 runner emits world_commit + turn_end
   5.2 controller appends assistant turn to JSONL
   5.3 controller commits final world JSON to disk
```

## 4) State and Dataflow Model (core of the report)
### 4.1 State structures in use
The actual runtime uses a plain `dict[str, Any]` alias called `State`. The `TypedDict` classes in `src/runtime/state.py` are descriptive, not enforced.

#### `state["task"]`
- **Created:** `new_runtime_state()`
- **Read by:** router, answer, prompt token builder
- **Mutated by:** router (`task.route`)
- **Key fields:**
  - `user_text`
  - `language`
  - `route` (runtime-added)

#### `state["runtime"]`
- **Created:** `new_runtime_state()`
- **Read by:** nodes, token builder, runner, controller, prompts
- **Mutated by:** runner, nodes, router/context/world nodes
- **Key fields observed in code:**
  - `node_trace`
  - `status`
  - `issues`
  - `now_iso`
  - `timezone`
  - `timestamp`
  - `turn_id`
  - `emitter` (**non-serializable runtime service inserted by runner**)
  - `context_builder_complete`, `context_builder_next`, `context_builder_status`
  - `world_modifier` (debug payload)

#### `state["context"]`
- **Created:** empty dict in `new_runtime_state()`
- **Read by:** answer, context builder, memory retriever, memory writer, token builder
- **Mutated by:** router prefill, context builder, memory retriever, memory writer
- **Observed fields:**
  - `sources`
  - `complete`
  - `next`
  - `issues`
  - `notes`
  - `memory_request`
  - nested legacy `context.sources`

This namespace is currently overloaded: it contains both evidence and control directives.

#### `state["final"]`
- **Created:** `new_runtime_state()`
- **Read by:** reflect_topics, memory_writer, UI finalization
- **Mutated by:** answer (`final.answer`)

#### `state["world"]`
- **Created:** copied from controller-owned durable world at turn start
- **Read by:** almost every node via prompts
- **Mutated by:** reflect_topics (`world.topics`), world_modifier tool results (`state["world"] = ...`)
- **Persisted by:** controller after turn if runner reports a final world

#### Temporary / private turn keys
- `_memory_writer_stored` in memory writer
- no current `_next_node` usage in active runtime

### 4.2 Durable world state vs per-turn working state
**Durable world state**
- file: `var/llm-thalamus-dev/state/world_state.json` in dev mode
- owner: `ControllerWorker`
- load/create: `controller.world_state.load_world_state()`
- commit: `controller.world_state.commit_world_state()`

**Per-turn working state**
- file-backed only indirectly through history/world commits
- assembled fresh per user message
- contains runtime-only references like the emitter

### 4.3 Dataflow pain points
1. `state["context"]` mixes:
   - evidence payloads,
   - control directives (`next`, `complete`),
   - diagnostic issues,
   - legacy nested `context.sources`.
   This will complicate scoped state views.

2. `state["runtime"]` includes a non-serializable emitter and several debug-only fields. Good for convenience, but it means “state” is not purely data.

3. Tool outputs are shaped inconsistently:
   - router prefill appends raw tool payload dicts into `context.sources`
   - context builder canonicalizes by `kind/title/records/meta`
   - memory retriever writes under `context.context.sources`
   This is the most immediate structural obstacle for deterministic `project_status` compilation and clean tool-boundary contracts.

4. The active runtime still depends on full-state visibility. There is no node projection layer yet.

## 5) Subsystem Deep Dives (module-by-module)
### UI layer
Responsibilities:
- render chat,
- display streaming output and internal logs,
- expose config editing,
- show current world and debug snapshots.

Key files:
- `F074` `src/ui/main_window.py`
- `F075` `src/ui/widgets.py`
- `F072` `src/ui/chat_renderer.py`
- `F073` `src/ui/config_dialog.py`

Coupling/hotspots:
- UI assumes exact event payload shapes from `runtime.events`.
- `MainWindow` directly reads `controller.world_state_path`, so some persistence knowledge leaks up into UI.

### Runtime / orchestrator layer
Responsibilities:
- compile graph,
- run a turn,
- emit protocol events,
- render prompts,
- centralize provider/tool loop behavior.

Key files:
- `F050`
- `F047`
- `F057`
- `F051`

Known coupling/hotspots:
- `nodes_common.py` is the largest change amplifier.
- `langgraph_runner.py` both runs the graph and performs debug snapshot shaping.

### Graph / nodes layer
Responsibilities:
- node registration and contracts,
- prompt selection,
- state mutations,
- tool permissions by node key.

Files:
- `src/runtime/nodes/*.py`
- `src/runtime/registry.py`

Hotspots:
- router mechanical prefill,
- context builder loop,
- world modifier result application,
- memory writer diagnostics placement.

### Tooling layer
Responsibilities:
- define schemas,
- bind handlers to resources,
- gate tools by node/skill,
- execute tool calls deterministically.

Files:
- `src/runtime/tool_loop.py`
- `src/runtime/tools/*`
- `src/runtime/skills/*`
- `src/controller/runtime_services.py`
- `src/controller/mcp/*`

Hotspots:
- duplicated/cross-cutting shaping of tool results into context,
- static provider explicit mapping requires code edits for every new tool,
- no tool discovery from MCP itself yet.

### Prompt/resources layer
Responsibilities:
- store prompt contracts,
- config template,
- graphics.

Files:
- `resources/prompts/*`
- `resources/config/config.json`
- `resources/graphics/*`

Hotspots:
- prompt tokens are centralized, which is good,
- but some prompt instructions and node code disagree on exact payload shapes.

### Persistence/data layer
Responsibilities:
- JSONL chat history,
- world JSON,
- MCP-backed memory access.

Files:
- `src/controller/chat_history.py`
- `src/controller/world_state.py`
- `src/runtime/tools/bindings/memory_query.py`
- `src/runtime/tools/bindings/memory_store.py`

Hotspots:
- docs claim SQLite stores, but code does not implement them,
- world state mutation path is in-memory until controller commit.

### Supporting utilities/scripts
Includes:
- tests/probes in `src/tests`
- documentation templates in `resources/Documentation`
- packaging in `Makefile` and desktop file

### Tests and dev tooling
The `src/tests` tree is mostly manual probes, LangChain experiments, and Ollama/LangGraph spikes. It is not a cohesive automated test suite.

## 6) Node Catalog
### `llm.router`
- **File:** `F084` `src/runtime/nodes/llm_router.py`
- **Purpose:** choose `answer`, `context`, or `world`.
- **Inputs:** `task.user_text`, `world`, `context`
- **Outputs:** `task.route`; optionally `runtime.issues`
- **Prompt:** `resources/prompts/runtime_router.txt`
- **Placeholders:** `<<CONTEXT_JSON>>`, `<<NOW_ISO>>`, `<<TIMEZONE>>`, `<<USER_MESSAGE>>`, `<<WORLD_JSON>>`
- **Tool policy:** mechanical prefill only, via node key `"router"` -> skills `core_context`, `mcp_memory_read`
- **Graph position:** entry node

### `llm.context_builder`
- **File:** `F080`
- **Purpose:** assemble evidence and decide next action.
- **Inputs:** `world`, `context`, `task.user_text`
- **Outputs:** `context.complete`, `context.next`, `context.issues`, optional `context.memory_request`
- **Prompt:** `resources/prompts/runtime_context_builder.txt`
- **Tool access:** node key `"context_builder"` -> chat history + memory read
- **Graph position:** selected when router routes `"context"`; can loop to memory retriever

### `llm.memory_retriever`
- **File:** `F081`
- **Purpose:** decide whether to call `memory_query` and append retrieval results.
- **Inputs:** `world.topics`, `context.memory_request`, `task.user_text`
- **Outputs:** appends retrieval evidence into `context`; issues note
- **Prompt:** `resources/prompts/runtime_memory_retriever.txt`
- **Tool access:** node key `"memory_retriever"` -> memory read only
- **Graph position:** loop body after context builder when requested

### `llm.world_modifier`
- **File:** `F085`
- **Purpose:** turn user instructions into allowed world mutations through `world_apply_ops`.
- **Inputs:** `world`, `task.user_text`
- **Outputs:** updates `state["world"]` from tool result; writes `runtime.status` and `runtime.world_modifier`
- **Prompt:** `resources/prompts/runtime_world_modifier.txt`
- **Tool access:** node key `"world_modifier"` -> world mutation only
- **Graph position:** selected when router routes `"world"`, then leads to answer

### `llm.answer`
- **File:** `F079`
- **Purpose:** generate final user-facing reply.
- **Inputs:** `world`, `context`, `runtime.status`, `runtime.issues`, `task.user_text`
- **Outputs:** `final.answer`
- **Prompt:** `resources/prompts/runtime_answer.txt`
- **Tool access:** none
- **Graph position:** terminal user-facing node before reflection

### `llm.reflect_topics`
- **File:** `F083`
- **Purpose:** update durable topic set for next turn.
- **Inputs:** `world.topics`, `task.user_text`, `final.answer`
- **Outputs:** `world.topics`
- **Prompt:** `resources/prompts/runtime_reflect_topics.txt`
- **Tool access:** none
- **Graph position:** after answer

### `llm.memory_writer`
- **File:** `F082`
- **Purpose:** store durable memory candidates through `memory_store`.
- **Inputs:** `task.user_text`, `final.answer`, `world`, `context`
- **Outputs:** diagnostic entries in `context`, tool-side durable write
- **Prompt:** `resources/prompts/runtime_memory_writer.txt`
- **Tool access:** node key `"memory_writer"` -> memory write only
- **Graph position:** final node before END

## 7) Tooling System Catalog
### Tool registry: declaration and discovery
There are two layers:

1. **Skill/catalog layer**
   - `src/runtime/skills/catalog/*.py`
   - each skill is a named bundle of tool names.

2. **RuntimeToolkit assembly**
   - `src/runtime/tools/toolkit.py`
   - loads known skills explicitly,
   - intersects them with `ENABLED_SKILLS`,
   - intersects again with `NODE_ALLOWED_SKILLS[node_key]`,
   - resolves each tool name through `StaticProvider.get(name)`.

This is explicit, not dynamic discovery.

### Tool loop parsing / validation / execution
Implemented in `src/runtime/tool_loop.py`:
- parse model-emitted tool args JSON
- validate args are a JSON object
- run handler
- validate result optionally
- normalize result to JSON string if needed
- append tool message into conversation

### Tool result formatting and reinjection
Reinjection mechanism:
```text
provider tool call -> ToolCall
-> handler(args_obj)
-> result_text
-> Message(role="tool", name=tool_name, tool_call_id=call_id, content=result_text)
-> appended to messages list
-> next provider round
```

### Logging
Present:
- `llm_request` events with provider payload and optional curl replay
- `log_line` for tool calls/results/errors
- final node output logging via `nodes_common.collect_text()`

Missing / weak:
- no consolidated audit trail of tool-call -> state mutation mapping
- no explicit structured event for each parsed tool call beyond generic stream/log handling
- no durable runtime log writer in snapshot code; only UI/manual logs included as artifacts

### Existing MCP client usage and boundaries
Good boundary today:
- nodes never import `controller.mcp.client`
- only tool bindings `memory_query` and `memory_store` call `resources.mcp.call_tool(...)`
- `build_runtime_services()` is the single wiring point for the MCP client

That aligns well with the desired “MCP isolated behind tool contracts” direction.

## 8) Persistence Catalog
### `world_state.json`
- **Schema source:** `controller.world_state.default_world()`
- **Fields observed:**
  - `updated_at`
  - `project`
  - `topics`
  - `goals`
  - `rules`
  - `identity.user_name`
  - `identity.session_user_name`
  - `identity.agent_name`
  - `identity.user_location`
  - optional `tz`
- **Load/save:** `load_world_state()`, `commit_world_state()`
- **Mutation rules in active runtime:**
  - in-turn mutation through `world_apply_ops` tool result and `reflect_topics`
  - durable commit only by controller after turn completes

### Memory/episodes DBs
Unknown from code snapshot as implemented stores. Documentation mentions SQLite memory/episodes DBs, but no runtime code or schema for those files exists in `src/`. What would confirm them: a storage module, migration/schema file, or tool binding pointing at sqlite.

### Caches, indexes, logs, file stores
Implemented:
- chat history JSONL
- world JSON
- MCP tools/list cache inside `MCPClient`
- manual debug logs shipped at repo root

### Backup/consistency considerations
- world commit is atomic-ish via temp file replace
- chat history append + trim rewrites tail window; corruption handling is minimal but acceptable for JSONL
- world tool does not commit directly; controller commit timing is the consistency boundary

## 9) Dependency & Call Graph Summaries
### Dependency overview by package/module
- `src/llm_thalamus.py` -> `config`, `controller.worker`, `ui.main_window`
- `src/controller/worker.py` -> controller persistence/services + runtime runner
- `src/runtime/langgraph_runner.py` -> graph builder + event system
- `src/runtime/graph_build.py` -> registry + node modules
- nodes -> `runtime.nodes_common`, `runtime.registry`, optionally `runtime.services`
- tool bindings -> `ToolResources`, some controller services (`world_state`)
- MCP client isolated under `src/controller/mcp/*`

### Key call chains
1. **App startup**
   - `src/llm_thalamus.py:main`
   - `config.bootstrap_config`
   - `ControllerWorker(...)`
   - `build_runtime_services(...)`

2. **User turn**
   - `ControllerWorker.submit_message`
   - `ControllerWorker._handle_message`
   - `runtime.deps.build_runtime_deps`
   - `runtime.state.new_runtime_state`
   - `runtime.langgraph_runner.run_turn_runtime`
   - `runtime.graph_build.build_compiled_graph`
   - node factory -> node callable
   - `runtime.nodes_common.run_*`
   - `runtime.tool_loop.chat_stream`
   - provider + tool handlers

3. **World mutation**
   - `llm_world_modifier` prompt/tool call
   - `runtime.tools.bindings.world_apply_ops.bind().handler`
   - `controller.world_state.load_world_state`
   - in-turn state replacement
   - post-turn controller commit

### Change amplifiers
- `F051` `src/runtime/nodes_common.py`
- `F039` `src/controller/worker.py`
- `F057` `src/runtime/tool_loop.py`
- `F047` `src/runtime/graph_build.py`
- prompt token contract in `GLOBAL_TOKEN_SPEC`

## 10) Per-File Inventory (complete)
See `audit_file_inventory.md`.

## 11) Strategic Fit Check (forward plan alignment)
### Obsidian as document store via MCP
**Where it plugs in today**
- new MCP-backed read tools under `src/runtime/tools/definitions/` + `bindings/`
- new skills under `src/runtime/skills/catalog/`
- allowlist updates in `src/runtime/tools/policy/node_skill_policy.py`
- prompt changes for router/context_builder so they request those tools appropriately

**Refactoring likely needed**
- canonical evidence shape for document/tool results
- a cleaner `context.sources` schema
- maybe a dedicated document-retrieval node if context_builder becomes too overloaded

**Prompt-only possibilities**
- router/context_builder behavior can be shifted toward new tools without structural graph changes

**Risks**
- if document retrieval results are appended in yet another ad hoc shape, context drift worsens
- mechanical vs LLM-triggered retrieval policy should be decided early

### MCP isolated behind tool contracts
This is already mostly true.
- Nodes do not import MCP code directly.
- `build_runtime_services()` is the wiring seam.
- Tool bindings own request shaping.

Recommended next step:
- keep all future MCP servers behind `ToolResources` and tool bindings, never in nodes

### Deterministic `project_status` compilation
No implementation present in snapshot.

Best fit:
- add a deterministic loader/compiler tool returning a stable JSON manifest
- expose it to router/context_builder as a read-only skill
- compile mechanically outside LLM nodes whenever feasible

Prompt-only scope:
- prompt can instruct when to use it, but the compiler itself should be mechanical code

### Scoped state views / per-node projections
Current system gives nodes full state dicts.
Best fit:
- projection layer in `run_structured_node` / `run_controller_node` / `run_streaming_answer_node`
- or graph wrappers that materialize node-specific views

Prompt-only scope:
- limited. Prompts can ask nodes to ignore fields, but actual visibility is still wide open.

### Future episodic SQLite ledger (shelved, contract-driven)
Best fit:
- implement as new tool(s) with deterministic schemas first
- keep nodes unaware of storage backend
- optionally add a retrieval skill later

This aligns well with the current tool-contract direction, but not with the current documentation claims that SQLite already exists.

## 12) Recommendations (incremental)
1. **Normalize `context` into one evidence schema**
   - **Why:** current mixed shapes are the biggest blocker for scoped state and deterministic manifests
   - **Files:** F080, F081, F082, F051
   - **Complexity/risk:** medium
   - **Type:** mechanical code

2. **Split control directives from evidence**
   - move `context.next`, `complete`, etc. into a dedicated state namespace such as `runtime.control` or `task.handoff`
   - **Files:** same as above + F047
   - **Complexity/risk:** medium
   - **Type:** mechanical code

3. **Refactor `nodes_common.py` into smaller modules**
   - token builder, JSON parsing, runner helpers, and mechanical prefill should not share one file
   - **Files:** F051
   - **Complexity/risk:** medium-high
   - **Type:** mechanical code

4. **Remove or quarantine legacy/unused runtime modules**
   - `runtime/build.py`, `runtime/graph_policy.py`, `runtime/prompt_loader.py`, `runtime/json_extract.py`, `runtime/providers/validate.py`, `runtime/tools/registry.py`
   - **Why:** reduce drift and audit surface
   - **Complexity/risk:** low-medium
   - **Type:** mechanical code

5. **Add one canonical structured event for each tool execution**
   - call, success/error, normalized result summary
   - **Files:** F057, F046, F039
   - **Complexity/risk:** medium
   - **Type:** mechanical code

6. **Keep MCP behind tool contracts and codify it in docs**
   - the code is already mostly there; update README/Developer README to match
   - **Files:** F004, F005
   - **Complexity/risk:** low
   - **Type:** mechanical/docs

7. **Add a read-only document-store skill scaffold**
   - for future Obsidian MCP integration
   - **Files:** `src/runtime/skills/catalog/*`, `src/runtime/tools/*`, `src/controller/runtime_services.py`
   - **Complexity/risk:** medium
   - **Type:** mechanical code

8. **Implement deterministic `project_status` as a tool, not a node**
   - **Why:** fits “prefer prompt tuning over code when feasible,” while keeping data compilation mechanical
   - **Files:** new tool definition/binding; prompt changes in router/context_builder
   - **Complexity/risk:** medium
   - **Type:** mechanical code + prompt tuning

9. **Introduce node-specific state projections**
   - **Why:** needed for long-term architecture discipline
   - **Files:** F051, F050, F047
   - **Complexity/risk:** high
   - **Type:** mechanical code

10. **Tighten config schema vs actual usage**
   - remove or mark unused fields like `use_episodes_db`, stale provider kinds, and old UI descriptions
   - **Files:** F018, F035
   - **Complexity/risk:** low-medium
   - **Type:** mechanical code/docs

11. **Update README claims to match code**
   - especially SQLite stores, graph order, and current world/memory architecture
   - **Files:** F004, F005, F001
   - **Complexity/risk:** low
   - **Type:** docs

12. **Add automated tests around active runtime seams**
   - focus on tool loop, world mutation, and prompt token coverage
   - **Files:** `src/tests/*` plus new tests
   - **Complexity/risk:** medium
   - **Type:** mechanical code

13. **Prompt-only pass: tighten router/context_builder/world_modifier contracts before code changes**
   - router: when to choose context vs world
   - context builder: one evidence schema only
   - memory writer: exact stored payload expectations
   - **Files:** prompt files under `resources/prompts/`
   - **Complexity/risk:** low
   - **Type:** prompt-only

14. **Move debug-only runtime fields out of primary state where practical**
   - emitter and verbose node debug payloads can live beside state, not inside it
   - **Files:** F050, F056, F039
   - **Complexity/risk:** medium
   - **Type:** mechanical code

15. **Document the actual world schema as a committed artifact**
   - best as `docs/architecture/world_state_schema.md`
   - **Files:** new docs + F040
   - **Complexity/risk:** low
   - **Type:** docs
