# Audit Overview

## Index

- `audit_overview.md` (this file): Sections 0–9, 11–12
- `audit_file_inventory.md`: Section 10 (Per-file inventory, IDs `F###`)
- `audit_appendix.md`: Supporting excerpts + unknowns

---

# llm_thalamus Architecture & Codebase Audit

## 0) Document Control

- **Snapshot identifier:** provided snapshot (zip sha256 55f23f19ecf7ca1e23fb4999807885952407c4fdc029679e58cfbbdce5d2c1b5)
- **Audit date:** 2026-02-28 (Africa/Windhoek)
- **How to use this document:**
  - Start with `audit_overview.md` for architecture + flow + subsystem deep dives + recommendations.
  - Use `audit_file_inventory.md` as the authoritative per-file index (IDs `F###` referenced throughout).
  - Use `audit_appendix.md` for supporting excerpts and “unknown from snapshot” checklists.
- **Conventions**
  - Paths are relative to repository root and shown exactly as in the snapshot.
  - **File IDs:** `F###` refer to entries in `audit_file_inventory.md`.
  - **“Unknown from snapshot”** means the code/config needed to confirm behavior is not present in this zip (or is generated at runtime).
  - “Node key” means the string passed to `RuntimeToolkit.toolset_for_node(node_key)` (e.g., `"router"`), not the `NODE_ID` (e.g., `"llm.router"`).

## 1) System Overview

### What the system does today (from snapshot)

`llm_thalamus` is a local desktop chat UI (PySide6) that runs a LangGraph state machine per user turn. Each turn:

- Loads/maintains a durable `world_state.json`
- Appends the user message to an on-disk JSONL chat history
- Runs a compiled LangGraph graph (`runtime.graph_build.build_compiled_graph`) which executes a fixed set of LLM-driven nodes
- Streams assistant output (from the `llm.answer` node) and “thinking/log” events to the UI
- Commits updated world state and (optionally) writes new “memories” via an MCP/OpenMemory tool contract

### Major subsystems

- **UI (PySide6)**: chat window, config dialog, renderers/widgets. (`src/ui/*`)
- **Controller / worker**: owns UI thread separation, chat history file I/O, world_state lifecycle, runtime wiring. (`src/controller/*`)
- **Runtime / orchestrator**: LangGraph runner, event bus/emitter, graph build + policy, provider abstraction. (`src/runtime/*`)
- **Graph / nodes**: LLM nodes registered in a registry and wired into the graph. (`src/runtime/nodes/*`)
- **Tooling subsystem**: deterministic streaming tool loop; “skills”→tool mapping; node skill policy allowlist; static tool provider binding to controller services and MCP. (`src/runtime/tool_loop.py`, `src/runtime/tools/*`, `src/runtime/skills/*`)
- **Persistence**:
  - Durable: `var/llm-thalamus-dev/state/world_state.json` (and configured location)
  - Semi-durable: chat history JSONL (`var/llm-thalamus-dev/data/chat_history.jsonl` via config)
  - Remote: MCP OpenMemory store via HTTP (optional)
- **Resources**: prompt templates and graphics. (`resources/prompts/*`, `resources/graphics/*`)

### High-level diagram (static)

```
[UI: MainWindow] 
      |
      v
[ControllerWorker] --(append user turn)--> [chat_history.jsonl]
      |                         |
      |                         v
      |                   [world_state.json] (load/commit)
      |
      v
[run_turn_runtime()]  ->  [LangGraph compiled graph]
      |                         |
      |                         +--> llm.router (prefill tools) 
      |                         +--> llm.context_builder (controller loop)
      |                         +--> llm.memory_retriever (tools)
      |                         +--> llm.world_modifier (tools)
      |                         +--> llm.answer (streams assistant text)
      |                         +--> llm.reflect_topics (structured JSON)
      |                         +--> llm.memory_writer (tools / MCP)
      |
      v
[TurnEmitter/EventBus] -> UI streams: assistant deltas, thinking deltas, logs, state snapshots
```

## 2) Repository Layout

### `.` (repo root)

- Project metadata and developer tooling:
  - `README.md` / `README_developer.md` / `CONTRIBUTING.md` / `LICENSE.md`
  - `Makefile`
  - Desktop launcher: `llm_thalamus.desktop`
  - Captured run logs: `thalamus-manual-*.log`, `thinking-manual-*.log`

**Hotspots:** `src/` (runtime), `resources/prompts/` (node behavior), `var/` (durable state/history).

### `resources/`

- `resources/prompts/`: prompt templates per node (`runtime_*.txt`)
- `resources/config/config.json`: default/installed config template
- `resources/graphics/`: UI assets (jpg/svg)
- `resources/Documentation/`: templates and prior audit docs shipped inside the repo

**Notable hotspot:** prompt token placeholders must be fully satisfied by `runtime.prompting.render_tokens` (raises on leftovers).

### `src/`

- `src/llm_thalamus.py`: main entrypoint (PySide6 UI boot)
- `src/config/`: config bootstrap + schema extraction and mode-dependent paths
- `src/controller/`: UI-facing worker, chat history, world state, MCP client
- `src/runtime/`: LangGraph graph build, nodes, tool loop, provider integration, event emission
- `src/ui/`: PySide6 windows, dialogs, widgets
- `src/tests/`: probes and smoke tests (LangChain/LangGraph/Ollama)

### `var/`

- Dev-mode runtime data roots:
  - `var/llm-thalamus-dev/data/chat_history.jsonl`
  - `var/llm-thalamus-dev/state/world_state.json`

## 3) Runtime Walkthrough (end-to-end)

This walkthrough is grounded in:

- UI entrypoint: `src/llm_thalamus.py:main()` (F0xx)
- Worker orchestration: `src/controller/worker.py:ControllerWorker._handle_message()` (F0xx)
- Turn runner: `src/runtime/langgraph_runner.py:run_turn_runtime()` (F0xx)
- Graph build: `src/runtime/graph_build.py:build_compiled_graph()` (F0xx)

### 3.1 Startup → UI boot

1. `src/llm_thalamus.py:main(argv)` calls `config.bootstrap_config(argv)` to produce a `ConfigSnapshot`.  
2. Prints a config summary (paths, provider settings, role models).  
3. Imports PySide6, constructs:
   - `ControllerWorker(cfg)` (runs on its own `QThread`)
   - `MainWindow(cfg, controller)` and shows UI.

**Unknown from snapshot:** packaging entrypoints (pip/console_scripts) are not present; the script is runnable via `python -m` only if installed accordingly.

### 3.2 User submits a message

1. UI calls `ControllerWorker.submit_message(text)` (Qt slot).
2. `submit_message()` spawns a Python thread and calls `_handle_message(text)`.

### 3.3 Controller persists input and builds runtime dependencies

Inside `_handle_message(text)`:

1. Persists the user turn to JSONL:
   - `controller.chat_history.append_turn(history_file, role="human", content=text, ...)`
2. Builds runtime dependencies:
   - `runtime.deps.build_runtime_deps(self._cfg)` (provider + prompt loader + role config)
3. Creates a fresh per-turn state:
   - `runtime.state.new_runtime_state(user_text=text)`
4. Copies durable world state into the turn:
   - `state["world"] = dict(self._world)`

### 3.4 Turn execution + event streaming

1. Controller iterates `for ev in runtime.langgraph_runner.run_turn_runtime(state, deps, self._runtime_services):`
2. `run_turn_runtime()`:
   - Compiles the LangGraph graph via `runtime.graph_build.build_compiled_graph(deps, services)`
   - Installs `TurnEmitter` into `state["runtime"]["emitter"]`
   - Emits `turn_start`
   - Runs the graph on a background thread (`compiled.invoke(state)`) while streaming events from `EventBus`
   - Emits state snapshots on `turn_start`, `node_start`, `node_end` via `_debug_state_view(state)`

### 3.5 Graph execution order (as wired today)

From `runtime.graph_build.build_compiled_graph()`:

1. Entry node: `router`
2. Conditional route:
   - `"context_builder"` if `state["task"]["route"] == "context"`
   - `"world_modifier"` if `state["task"]["route"] == "world"`
   - default `"answer"`
3. Context controller loop:
   - `context_builder` may route to `memory_retriever`, then loops back to `context_builder`
4. World modifier path:
   - `world_modifier -> answer`
5. End-of-turn pipeline:
   - `answer -> reflect_topics -> memory_writer -> END`

### 3.6 Tool loop behavior and tool result injection

Nodes never call tools “directly”; tool calls happen through `runtime.tool_loop.chat_stream()`:

- Provider is called in streaming mode.
- If tools are enabled for this node call, the tool loop:
  1. Runs tool-capable rounds with `response_format=None` so tool calls can occur.
  2. Executes tool calls deterministically via local handlers (and optional validators).
  3. Appends `Message(role="tool", ...)` tool result messages back into the message list.
  4. When tool calls stop, an optional final formatting pass is made with tools disabled and `response_format` enforced.

Some nodes (notably `llm.router`) also run a **mechanical prefill** using the same handlers via `runtime.nodes_common.run_tools_mechanically(...)` before making the LLM call.

### 3.7 Persistence updates and UI events

At the end of `run_turn_runtime()`:

- Emits a best-effort `world_commit` event derived from `out["world"]` vs `state["world"]`.
- Emits `turn_end_ok` (or `turn_end_error`).

In the controller, on relevant events:

- Streams assistant deltas to the chat bubble (from `assistant_*` events emitted by the answer node).
- Updates UI “thinking” window from `delta_thinking` and per-node headers.
- Commits the durable world state file via `controller.world_state.commit_world_state(...)` when the turn completes (see `ControllerWorker._handle_message` logic).

### 3.8 Textual sequence diagram

```
UI -> ControllerWorker.submit_message(text)
  -> append_turn(chat_history.jsonl)
  -> new_runtime_state(user_text)
  -> state.world = loaded world_state.json
  -> run_turn_runtime(state, deps, services)
     -> build_compiled_graph()
     -> install TurnEmitter into state.runtime.emitter
     -> emit turn_start
     -> invoke LangGraph (background thread)
        router -> (context_builder loop?) -> answer -> reflect_topics -> memory_writer
           each node:
             - emit node_start
             - provider.chat_stream (with optional tool_loop)
             - emit assistant deltas (answer only)
             - emit node_end
     -> emit world_commit
     -> emit turn_end_ok
  -> commit_world_state(world_state.json)
```

## 4) State and Dataflow Model (core)

### 4.1 Canonical per-turn State shape

The runtime uses a plain `dict[str, Any]` called `State` (type alias) with a *loosely-typed* schema defined in `src/runtime/state.py`:

- `state["task"]`: user request and routing intent
- `state["runtime"]`: per-turn runtime metadata (trace, status, issues, time context, emitter)
- `state["context"]`: retrieval/context aggregation scratch space
- `state["final"]`: assistant output
- `state["world"]`: durable world state (copied in at turn start; later mutated)

Creation point:
- `src/runtime/state.py:new_runtime_state(user_text=...)`

### 4.2 Durable world state vs per-turn working state

**Durable world state**
- File: `var/llm-thalamus-dev/state/world_state.json` (F112) in dev mode (path can vary by config).
- Load/create: `src/controller/world_state.py:load_world_state(path, now_iso, tz)` (F0xx)
- Commit: `src/controller/world_state.py:commit_world_state(path, world)` (F0xx)

`ControllerWorker` loads durable world state at startup and stores it in `self._world`. For each turn, it copies it into `state["world"]` before graph execution.

**Per-turn state**
- Lives only in memory during `run_turn_runtime()` execution.
- After the graph, the controller decides what to commit to disk (world updates, chat history, etc.).

### 4.3 State structures, owners, and mutations

#### `state["task"]` (RuntimeTask)

- Created: `new_runtime_state()`
- Read by:
  - `llm.router` (`task.user_text`)
  - all other nodes (`task.user_text`)
- Mutated by:
  - `llm.router.apply_result()` sets `state["task"]["route"]` (string)
- Key fields observed in code:
  - `user_text: str`
  - `language: str` (initialized to `"en"`, not otherwise used in snapshot)
  - `route: str` (added by router; values implied by graph: `"context"`, `"world"`, default other)

#### `state["runtime"]` (RuntimeRuntime + internals)

- Created: `new_runtime_state()`, then enriched in `run_turn_runtime()`
- Read by:
  - Answer node (status, issues, now_iso, timezone)
  - Graph build (context hop counter `context_hops` if present)
- Mutated by:
  - `run_turn_runtime()` installs:
    - `runtime["emitter"]` (non-serializable, stripped by debug snapshot)
    - `runtime["turn_id"]` (uuid hex)
    - `runtime["now_iso"]`, `runtime["timezone"]`, and optional `runtime["timestamp"]`
  - `nodes_common.append_node_trace()` appends to `runtime["node_trace"]`
  - Router optionally stores `runtime["issues"]` from model output
- Notable fields (seen in code, but not formalized in `TypedDict`):
  - `emitter` (TurnEmitter instance)
  - `turn_id` (uuid)
  - `timestamp` (int epoch seconds; best-effort)

**Pain point for scoped state views:** `runtime` mixes user-relevant metadata, debugging internals, and a live emitter object.

#### `state["context"]` (RuntimeContext but used as “context controller packet”)

This is the most schema-inconsistent object across the snapshot.

- Created: as `{}` in `new_runtime_state()`
- Mutated/read by:
  - `llm.router` writes/extends `context["sources"]` (list) with mechanical tool results
  - `llm.context_builder` (controller node) reads/writes:
    - `context["complete"]`, `context["issues"]`, `context["next"]`/`next_node`/`route`
    - may also manage `context["sources"]` or nested `context["context"]` depending on prompt evolution
  - `llm.memory_retriever` writes memory evidence into `context` (see node file)
  - `llm.memory_writer.apply_result()` writes:
    - `context["issues"]` (adds `"memory_writer: stored_count=..."`)
    - `context["context"]["sources"]` (nested) with a diagnostic note item

**Pain point:** simultaneous use of:
- `context["sources"]` (flat) **and**
- `context["context"]["sources"]` (nested)

This will complicate:
- deterministic `project_status` compilation
- scoped per-node views (what is “the context”?)
- tool contract boundaries (where evidence packets live)

#### `state["final"]` (RuntimeFinal)

- Created: `new_runtime_state()` sets `final["answer"]=""`
- Mutated by:
  - `llm.answer` sets `final["answer"]` to full streamed text
- Read by:
  - `llm.reflect_topics` (needs most recent assistant output)
  - `llm.memory_writer` (needs assistant answer for memory decisions)

#### `state["world"]` (durable world snapshot)

- Initialized by controller per turn from durable file.
- Mutated by:
  - `llm.reflect_topics` sets `world["topics"]`
  - `llm.world_modifier` applies world operations (via tools)
  - Potentially other nodes (prompt-driven) depending on how tool results are applied.

### 4.4 Current pain points impacting strategic goals

- **Schema drift in `context`:** flat vs nested sources, multiple alias keys (`next`, `next_node`, `route`).
- **Emitter in runtime state:** breaks “JSON-only state” assumptions; runner compensates with sanitization.
- **World-state mutation boundaries:** world changes can happen in multiple nodes (world_modifier + reflect_topics).
- **Tool evidence normalization:** tool results appear as raw JSON blobs in `context.sources` without a single enforced schema.

## 5) Subsystem Deep Dives (module-by-module)

### 5.1 UI layer (`src/ui/*`)

**Responsibilities**
- Render chat turns (including streaming assistant output).
- Provide a config dialog and world-state summary widgets.
- Bridge UI actions to `ControllerWorker` slots/signals.

**Key modules**
- `src/ui/main_window.py` (F104)
- `src/ui/chat_renderer.py` (F102)
- `src/ui/config_dialog.py` (F103)
- `src/ui/widgets.py` (F105)

**Public interfaces**
- Consumes Qt signals from `ControllerWorker`:
  - assistant stream: `assistant_stream_start/delta/end`
  - thinking: `thinking_started/delta/finished`
  - history: `history_turn`
  - logs/state/world updates

**Dependencies**
- Depends on `src/controller/worker.py` for all non-trivial operations.
- Uses `resources/graphics/*` for status imagery.

**Coupling / hotspots**
- UI assumes a certain event schema (`TurnEventFactory`), but event types are defined in runtime (`src/runtime/events.py`) and emitted in nodes/runner.

### 5.2 Controller / worker layer (`src/controller/*`)

**Responsibilities**
- Owns durable file paths and lifecycle:
  - chat history JSONL
  - world_state.json
- Wires runtime dependencies:
  - builds provider + roles (`runtime.deps`)
  - builds tool resources + toolkit (`controller.runtime_services`)
- Runs the per-turn LangGraph runtime and forwards streaming events to UI.

**Key modules**
- `src/controller/worker.py` (F036) — orchestration + Qt signals
- `src/controller/world_state.py` (F037) — load/commit world
- `src/controller/chat_history.py` (F031) — JSONL append/read/trim
- `src/controller/chat_history_service.py` (F032) — service wrapper used by tools
- `src/controller/runtime_services.py` (F035) — builds `RuntimeServices`
- `src/controller/mcp/*` (F033, F034) — MCP HTTP client

**Public interfaces**
- `ControllerWorker.submit_message(text)` (Qt slot)
- `ControllerWorker.emit_history()` to re-emit history into UI

**Dependencies**
- Depends on runtime runner (`run_turn_runtime`) and runtime deps builder.
- MCP client is only used through tool bindings (controller wires it into `ToolResources`).

**Coupling / hotspots**
- Controller owns “truth” of world state file and commits; runtime also produces `world_commit` events (dual reporting).
- `mcp_openmemory_user_id` is derived from API key in `build_runtime_services()`; this is a design choice worth reviewing (see Recommendations).

### 5.3 Runtime / orchestrator layer (`src/runtime/*`)

**Responsibilities**
- Build and run the LangGraph graph.
- Provide streaming event model: `EventBus`, `TurnEmitter`, `TurnEventFactory`.
- Provide provider abstraction (Ollama) and streaming tool loop.

**Key modules**
- `src/runtime/graph_build.py` (F045) — authoritative graph wiring
- `src/runtime/langgraph_runner.py` (F049) — turn runner + event streaming
- `src/runtime/tool_loop.py` (F074) — deterministic tool loop
- `src/runtime/nodes_common.py` (F058) — canonical node runners
- `src/runtime/providers/*` (F063) — provider implementation
- `src/runtime/prompting.py` (F060) — token replacement + unresolved-token guard
- `src/runtime/prompt_loader.py` (F059) — reads prompt files

**Public interfaces**
- `run_turn_runtime(state, deps, services) -> Iterator[TurnEvent]`
- `build_compiled_graph(deps, services) -> compiled graph`

**Dependencies**
- Depends on LangGraph (`langgraph.graph.StateGraph`).
- Providers depend on HTTP calls to Ollama (details in `runtime/providers/ollama.py`).

**Coupling / hotspots**
- Prompt token strictness: any leftover `<<TOKEN>>` aborts the node (and can abort the turn).
- Some behavior is duplicated between `src/runtime/build.py` and `src/runtime/graph_build.py` (two graph builders).

### 5.4 Graph / nodes layer (`src/runtime/nodes/*`)

**Responsibilities**
- Each node defines:
  - Prompt file
  - Tool policy (via node_key)
  - Apply-result function that mutates `State`
  - Registration via `runtime.registry.register(NodeSpec(...))`

**Key modules**
- Node implementations: `src/runtime/nodes/llm_*.py` (see Node Catalog §6)
- Registry: `src/runtime/registry.py` (F066)

**Coupling / hotspots**
- Nodes encode state schema assumptions directly (not mediated by projections).
- Some nodes use mixed context schema (flat vs nested sources).

### 5.5 Tooling layer (`src/runtime/tools/*` + `src/runtime/skills/*`)

**Responsibilities**
- Expose tools to nodes as “skills”:
  - skills registry (`runtime/skills/registry.py`)
  - node allowlist (`runtime/tools/policy/node_skill_policy.py`)
  - static provider binding tool names to handlers (`runtime/tools/providers/static_provider.py`)
- Bind tool handlers to concrete resources:
  - chat history service
  - world state file path
  - MCP client

**Key modules**
- Tool loop: `src/runtime/tool_loop.py` (F074)
- Toolkit assembly: `src/runtime/tools/toolkit.py` (F087)
- Skills catalog: `src/runtime/skills/catalog/*` (F068, etc.)
- Tool bindings: `src/runtime/tools/bindings/*` (F076, etc.)
- Tool definitions (schemas): `src/runtime/tools/definitions/*`

**Coupling / hotspots**
- Tool schemas are duplicated (definitions vs bindings) and must stay in sync.
- MCP/OpenMemory semantics leak slightly into bindings (e.g., hard-coded tool name `openmemory_query`).

### 5.6 Prompt/resources layer (`resources/prompts/*`)

**Responsibilities**
- Provide per-node prompt templates using `<<TOKEN>>` placeholders.
- Node files choose prompt by `PROMPT_NAME`, loaded via `deps.load_prompt(name)`.

**Key files**
- `resources/prompts/runtime_router.txt` (F023)
- `resources/prompts/runtime_context_builder.txt` (F019)
- `resources/prompts/runtime_memory_retriever.txt` (F020)
- `resources/prompts/runtime_world_modifier.txt` (F024)
- `resources/prompts/runtime_answer.txt` (F018)
- `resources/prompts/runtime_reflect_topics.txt` (F022)
- `resources/prompts/runtime_memory_writer.txt` (F021)

**Hotspot**
- Token mismatch between prompt template and node-provided token dict is a hard failure (`render_tokens`).

### 5.7 Persistence/data layer

- `world_state.json` lifecycle: `src/controller/world_state.py`
- chat history JSONL lifecycle: `src/controller/chat_history.py` + `chat_history_service.py`
- remote memory store via MCP/OpenMemory: `src/controller/mcp/*` plus tool bindings in `src/runtime/tools/bindings/*`

### 5.8 Supporting utilities/scripts

- Config boot and schema: `src/config/*`
- `.continue/*` rules and MCP server config templates (dev tooling, not runtime code)
- `resources/Documentation/*` includes prior audit docs and templates (not used by runtime)

### 5.9 Tests and dev tooling (`src/tests/*`)

These are mostly probes/spikes:
- LangChain prompt/template and output parser experiments
- LangGraph + Ollama router tests
- Interactive Ollama chat script

**Unknown from snapshot:** automated CI configuration (GitHub Actions, etc.) not present.

## 6) Node Catalog

Nodes are registered via `runtime.registry.register(NodeSpec(...))` in each `src/runtime/nodes/llm_*.py` module.

### 6.1 Graph order and adjacency

- Graph wiring is defined in `src/runtime/graph_build.py` (F045).
- Nominal flow:
  - `router` → `context_builder` → (`memory_retriever` ↔ `context_builder` loop)* → `answer` → `reflect_topics` → `memory_writer` → END
  - `router` → `world_modifier` → `answer` → ...

### 6.2 Nodes (per node)

#### llm.answer

- **Implementation:** `src/runtime/nodes/llm_answer.py` (F051)
- **Prompt:** `resources/prompts/runtime_answer.txt` (F018)
- **Prompt placeholders:** `CONTEXT_JSON`, `ISSUES_JSON`, `NOW_ISO`, `STATUS`, `TIMEZONE`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** tools disabled in this node call
- **Reads (observed top-level keys):** `context`, `runtime`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `final`

#### llm.context_builder

- **Implementation:** `src/runtime/nodes/llm_context_builder.py` (F052)
- **Prompt:** `resources/prompts/runtime_context_builder.txt` (F019)
- **Prompt placeholders:** `EXISTING_CONTEXT_JSON`, `NODE_ID`, `ROLE_KEY`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** node key `context_builder` → skills ['core_context', 'mcp_memory_read'] → tools ['chat_history_tail', 'memory_query']
- **Reads (observed top-level keys):** `context`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `context`, `runtime`

#### llm.memory_retriever

- **Implementation:** `src/runtime/nodes/llm_memory_retriever.py` (F053)
- **Prompt:** `resources/prompts/runtime_memory_retriever.txt` (F020)
- **Prompt placeholders:** `CONTEXT_JSON`, `NODE_ID`, `NOW_ISO`, `REQUESTED_LIMIT`, `ROLE_KEY`, `TIMEZONE`, `TOPICS_JSON`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** node key `memory_retriever` → skills ['mcp_memory_read'] → tools ['memory_query']
- **Reads (observed top-level keys):** `context`, `runtime`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `context`

#### llm.memory_writer

- **Implementation:** `src/runtime/nodes/llm_memory_writer.py` (F054)
- **Prompt:** `resources/prompts/runtime_memory_writer.txt` (F021)
- **Prompt placeholders:** `ASSISTANT_ANSWER`, `CONTEXT_JSON`, `NODE_ID`, `NOW_ISO`, `ROLE_KEY`, `TIMEZONE`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** node key `memory_writer` → skills ['mcp_memory_write'] → tools ['memory_store']
- **Reads (observed top-level keys):** `context`, `final`, `runtime`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `context`

#### llm.reflect_topics

- **Implementation:** `src/runtime/nodes/llm_reflect_topics.py` (F055)
- **Prompt:** `resources/prompts/runtime_reflect_topics.txt` (F022)
- **Prompt placeholders:** `ASSISTANT_MESSAGE`, `PREV_TOPICS_JSON`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** tools disabled in this node call
- **Reads (observed top-level keys):** `final`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `world`

#### llm.router

- **Implementation:** `src/runtime/nodes/llm_router.py` (F056)
- **Prompt:** `resources/prompts/runtime_router.txt` (F023)
- **Prompt placeholders:** `NOW`, `TZ`, `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** mechanical prefill uses node key `router` → skills ['core_context', 'mcp_memory_read'] → tools ['chat_history_tail', 'memory_query']; LLM call itself runs with tools disabled (`node_key_for_tools=None`), relying on the prefill.
- **Reads (observed top-level keys):** `context`, `runtime`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `context`

#### llm.world_modifier

- **Implementation:** `src/runtime/nodes/llm_world_modifier.py` (F057)
- **Prompt:** `resources/prompts/runtime_world_modifier.txt` (F024)
- **Prompt placeholders:** `USER_MESSAGE`, `WORLD_JSON`
- **Tool access policy:** node key `world_modifier` → skills ['core_world'] → tools ['world_apply_ops']
- **Reads (observed top-level keys):** `runtime`, `task`, `world`
- **Mutates (observed top-level keys via `setdefault`):** `runtime`


## 7) Tooling System Catalog

### 7.1 Tool registry / discovery

Tool availability is assembled at runtime by **skills + policy** (not dynamic discovery):

1. **Enabled skills registry:** `src/runtime/skills/registry.py` (F072) defines `ENABLED_SKILLS`.
2. **Skill catalogs:** `src/runtime/skills/catalog/*.py` map skill → tool names (e.g., `core_context` → `chat_history_tail`).
3. **Node allowlist policy:** `src/runtime/tools/policy/node_skill_policy.py` (F083) maps node key → allowed skills.
4. **Toolkit assembly:** `src/runtime/tools/toolkit.py` (F087) intersects enabled skills with node-allowed skills and constructs a `ToolSet` (defs + handlers + validators).

This is an explicit “capability firewall” design: nodes cannot access tools unless permitted by policy.

### 7.2 Tool schemas vs tool bindings

Each tool name has (at least) two modules:

- **Definition:** `src/runtime/tools/definitions/<tool>.py` — provides the `ToolDef` schema sent to the LLM provider.
- **Binding:** `src/runtime/tools/bindings/<tool>.py` — provides the deterministic handler bound to `ToolResources`.

The static provider `src/runtime/tools/providers/static_provider.py` (F084) wires names to both.

**Risk:** schema/binding drift (no single-source-of-truth). The snapshot does not show an automated consistency check.

### 7.3 Tool loop: parse → validate → execute → inject

Implemented in `src/runtime/tool_loop.py` (F074):

- Parses tool call args as JSON (with a “double-encoded JSON” guard).
- Requires args to be a JSON object (dict).
- Executes handler, optionally validates result (per-tool validator).
- Normalizes tool result to a string (JSON-dumps if non-string).
- Appends `Message(role="tool", name=..., tool_call_id=..., content=...)` to the chat message list for the next round.

**Format enforcement strategy**
- While tools are available: `response_format=None` to allow tool calls.
- When tool calls stop: optional final formatting pass with tools disabled and `response_format` enforced (JSON-mode prompts).

### 7.4 Tool result injection into model context

Tool results are injected as standard tool messages (`role="tool"`). This injection occurs inside the tool loop; nodes see tool results only because they re-render prompts in later rounds (controller nodes) or because the provider is invoked with tool results in the message list.

Additionally, nodes may store tool output in `state["context"]["sources"]` as “evidence packets” (router prefill does this).

### 7.5 Logging and diagnostics

- Each tool call emits a compact log line when an emitter is provided:

  `"[tool] call <name> args=<json>"`

- Tool errors do not crash the turn; they are:
  - logged as `"[tool] error <name>: <err>"`
  - injected to the model as `{"ok": false, "error": {"message": "..."}}`

### 7.6 MCP boundaries

MCP is accessible only through `ToolResources.mcp` (wired by the controller) and tool bindings:

- `memory_query` uses `MCPClient.call_tool("openmemory", name="openmemory_query", ...)`
- `memory_store` similarly calls an OpenMemory write tool (see binding)

Nodes do not import the MCP client directly in this snapshot (aligned with “tool contract boundary” goal), but the bindings embed OpenMemory-specific tool names.

### 7.7 What’s missing (unknown from snapshot)

- No dynamic tool discovery from MCP (`tools/list`) is used in runtime toolkit assembly (client supports it, toolkit does not).
- No tool-call transcript persistence format beyond logs and `context.sources`.

## 8) Persistence Catalog

### 8.1 `world_state.json`

- **Default schema constructor:** `src/controller/world_state.py:default_world(now_iso, tz)` (F037)
- **Load/create:** `load_world_state(path, now_iso, tz)`
  - Creates file if missing.
  - If JSON is corrupted or not an object, resets to defaults (non-failing boot).
  - Updates `updated_at` on load if `now_iso` provided.
- **Commit:** `commit_world_state(path, world)`
  - Writes to `*.tmp` then replaces (atomic-ish).

**Observed keys in default world**
- `updated_at: str`
- `project: str`
- `topics: list`
- `goals: list`
- `rules: list`
- `identity: {user_name, session_user_name, agent_name, user_location}`
- optional `tz`

**Mutation points**
- `llm.reflect_topics` overwrites `world["topics"]` with model output.
- `llm.world_modifier` applies ops via `world_apply_ops` tool.

### 8.2 Chat history (JSONL)

- **File service:** `src/controller/chat_history_service.py:FileChatHistoryService` (F032)
- **Low-level ops:** `src/controller/chat_history.py`
  - `append_turn(...)`
  - `read_tail(...)`
  - trimming behavior via `max_turns` / `message_history_max`

**Schema**
- Each line is JSON for a single turn record (role, content, ts). Exact fields are defined in `controller.chat_history`.

**Usage**
- UI reads tail on load and emits to view.
- Tool `chat_history_tail` reads tail via the `chat_history` ToolResource.

### 8.3 Memory store (remote, via MCP/OpenMemory)

- **Client:** `src/controller/mcp/client.py:MCPClient` (F033)
- **Transport:** `src/controller/mcp/transport_streamable_http.py`
- **Tool bindings:**
  - `src/runtime/tools/bindings/memory_query.py` (F076)
  - `src/runtime/tools/bindings/memory_store.py` (F077)

**Unknown from snapshot**
- Exact OpenMemory tool schemas and returned JSON structure beyond what bindings parse.
- Any retention policy, deduplication strategy, or “sector” semantics beyond optional parameters.

### 8.4 Other durable artifacts

- Manual logs in repo root (`thalamus-manual-*.log`, `thinking-manual-*.log`) appear to be captured runs, not runtime-managed logs.
- Runtime log file path is configured via `ConfigSnapshot.log_file`; log writer implementation is in `runtime.emitter` + UI wiring.

### 8.5 Backup/consistency considerations (based on code)

- `world_state.json` is written via replace; safe against partial writes but not versioned.
- chat history trimming rewrites JSONL when exceeding max (see implementation).
- No explicit locking around these files; concurrent processes may race (unknown if multi-process is expected).

## 9) Dependency & Call Graph Summaries

### 9.1 Package/module dependency overview (static)

At a coarse level:

- `src/llm_thalamus.py` depends on:
  - `src/config/*`
  - `src/controller/worker.py`
  - `src/ui/*`
- `src/controller/*` depends on:
  - `src/runtime/*` (deps builder, runner, state)
  - `src/controller/mcp/*` (optional)
- `src/runtime/*` depends on:
  - LangGraph (`langgraph.graph`)
  - Provider(s) in `src/runtime/providers/*`
  - Prompt resources under `resources/prompts/*`
- `src/runtime/tools/*` depends on:
  - `src/controller` only indirectly via `ToolResources` wired by controller (runtime code itself does not import controller modules)

**Note:** This is based on import graph inspection; runtime behavior can still couple subsystems via shared state schema.

### 9.2 Key call chains (entrypoint → critical leaf functions)

#### UI boot

`llm_thalamus.py:main()`  
→ `config.bootstrap_config()`  
→ `ControllerWorker(cfg)`  
→ `MainWindow(cfg, controller).show()`

#### Per turn (happy path)

`ControllerWorker.submit_message(text)`  
→ `_handle_message(text)`  
→ `controller.chat_history.append_turn(...)`  
→ `runtime.deps.build_runtime_deps(cfg)`  
→ `runtime.state.new_runtime_state(user_text=text)`  
→ `run_turn_runtime(state, deps, runtime_services)`  
→ `runtime.graph_build.build_compiled_graph(deps, services)`  
→ `compiled.invoke(state)` executes nodes  
→ `TurnEmitter` events streamed to UI  
→ controller commits updated world state

#### Tool call chain (during a node)

`nodes_common.run_structured_node()`  
→ `tool_loop.chat_stream()`  
→ `provider.chat_stream()` yields `StreamEvent(type="tool_call")`  
→ `tool_loop` executes handler from `ToolSet.handlers`  
→ `ToolResources` (chat history/world/MCP) used by binding  
→ tool result appended as `Message(role="tool")`  
→ provider called again for next round / formatting pass

### 9.3 Change amplifiers (ripple risks)

- **Prompt token strictness** (`runtime.prompting.render_tokens`): any placeholder drift breaks the node at runtime.
- **`state["context"]` schema drift**: multiple nodes assume different shapes; small change can cascade.
- **Tool schema/binding duplication**: updates must be made in multiple places to keep defs and handlers aligned.
- **Graph wiring centrality** (`runtime.graph_build.py`): node IDs, node keys, and routing strings must stay consistent with prompts.

### 9.4 Uncertainty notes

This section is best-effort based on static code inspection:
- The exact provider request/response schemas depend on the `runtime.providers.*` implementation and external Ollama behavior.
- Runtime file paths depend on config resolution (`src/config/*`) and whether the app is run in dev vs installed mode.

## 11) Strategic Fit Check (forward plan alignment)

This section evaluates the snapshot against the stated direction and identifies concrete integration points.

### 11.1 Obsidian as document store (over MCP)

**Where it would plug in today**
- The runtime already treats persistence as a tool boundary:
  - Tools are wired through `ToolResources` and invoked via tool loop.
- A future “docs query” tool would fit naturally as:
  - New skill (e.g., `mcp_docs_read`)
  - New tools under `src/runtime/tools/definitions/*` and `bindings/*`
  - Node policy updates in `src/runtime/tools/policy/node_skill_policy.py`

**Likely refactoring**
- Introduce a `docs_query` tool and ensure context builder prompt expects/uses it.
- Keep MCP specifics inside bindings; extend `MCPClient` usage if Obsidian MCP server has different behaviors.

**Prompt-only opportunities**
- Router prompt can be tuned to route to `context_builder` when user references “that doc/file/note” even before docs tool exists (but won’t retrieve).

**Risks**
- Without a standardized evidence packet schema, adding docs results risks worsening `context` schema drift.

### 11.2 MCP isolated behind tool contracts; nodes never call MCP directly

**Current status (from snapshot)**
- Good: node modules do not import `controller.mcp.*`.
- MCP is only reachable via `ToolResources.mcp` and bindings (`memory_query`, `memory_store`).

**What likely needs tightening**
- OpenMemory tool names (`openmemory_query`, etc.) are hard-coded in bindings. If the goal is “MCP generic,” encapsulate tool name mapping in a provider layer.

### 11.3 Deterministic `project_status` manifest compiled mechanically

**Where it would plug in**
- Natural placement:
  - `src/controller/worker.py` after turn completion (it already has access to final `state` and to durable paths).
  - Or inside runtime after `world_commit` emission, as a separate mechanical step.

**What needs refactoring**
- Enforce a stable schema for `state["context"]` and evidence packets.
- Clearly separate “debug/diagnostic” from “status manifest inputs”.
- Decide canonical sources:
  - world state
  - recent chat tail
  - retrieved evidence packets
  - tool call trace summary

**Prompt-only opportunities**
- Some portions (like a human-readable status summary) can be produced by an LLM node, but the goal says “compiled mechanically”, so prompts should not be authoritative.

### 11.4 Scoped state views / per-node projections

**Where it would plug in**
- Node runners live in `src/runtime/nodes_common.py`. This is the best choke-point to:
  - Construct a per-node view (projection) from full `State`
  - Render prompt from that view
  - Apply a constrained patch back to full state

**What needs refactoring**
- Replace direct node access to `state` with an interface:
  - `view = project_state(state, node_id)`  
  - `patch = node(view)`  
  - `state = apply_patch(state, patch)`
- Resolve the `context` schema drift first, otherwise projections become guesswork.

**Prompt-only opportunities**
- Prompts can be tuned to “pretend the view is limited,” but code currently still passes full JSON blobs (world/context) to prompts.

### 11.5 Prefer prompt tuning over code when feasible

**Current status**
- Strong: node behaviors are largely prompt-defined; nodes are small shells around prompt execution.
- Strict token enforcement (`render_tokens`) encourages disciplined prompt evolution.

**What could be improved without code**
- Router routing criteria and “need” fields can be improved entirely in `resources/prompts/runtime_router.txt`.
- Context builder “next” decision and evidence selection can likely be improved mostly in prompt.

**Where code is still needed**
- Enforcing state projections, canonicalizing context schema, and adding new tool types.

### 11.6 Future episodic SQLite ledger (shelved, contract-driven)

**Where it would plug in**
- Add new tools (read/write) via skills, similar to memory tools.
- Keep SQLite behind tool handlers, not imported by nodes.

**Risks**
- If “episodes” are appended into `context` without a schema, `context` drift will worsen. Canonicalize evidence packets first.

## 12) Recommendations (incremental)

Prioritized actions (higher impact first). Complexity/risk are relative to the current snapshot.

1. **Canonicalize `state['context']` schema (single `sources` location + typed envelope).**
   - Why: Current snapshot uses both `context['sources']` and `context['context']['sources']`, causing drift and downstream fragility.
   - Files/modules: src/runtime/state.py (F073), src/runtime/nodes_common.py (F058), src/runtime/nodes/llm_router.py (F056), src/runtime/nodes/llm_context_builder.py (F052), src/runtime/nodes/llm_memory_retriever.py (F053), src/runtime/nodes/llm_memory_writer.py (F054)
   - Complexity/risk: **high**
   - Category: **Mechanical code**

2. **Add a mechanical validator for prompt placeholders at startup (fail fast with file+token).**
   - Why: Today unresolved tokens fail at runtime mid-turn; validate `resources/prompts/*.txt` against node token dicts or at least list tokens.
   - Files/modules: src/runtime/prompting.py (F060), src/runtime/nodes/*.py, resources/prompts/*.txt
   - Complexity/risk: **med**
   - Category: **Mechanical code**

3. **Unify graph building: deprecate `src/runtime/build.py` or make it a thin wrapper around `graph_build.py`.**
   - Why: Two graph builders increase confusion and risk of divergence.
   - Files/modules: src/runtime/build.py (F040), src/runtime/graph_build.py (F045)
   - Complexity/risk: **low**
   - Category: **Mechanical code**

4. **Make `mcp_openmemory_user_id` a dedicated config field; stop deriving it from API key.**
   - Why: Current wiring uses API key as user_id fallback, which is surprising and can leak secrets into stored metadata.
   - Files/modules: src/controller/runtime_services.py (F035), resources/config/config.json (F012), src/config/_schema.py (F030)
   - Complexity/risk: **med**
   - Category: **Mechanical code**

5. **Introduce an “evidence packet” schema and helper constructors in one module.**
   - Why: Tool outputs are currently raw dicts; standardize `kind/title/items/meta` to support deterministic `project_status` and scoped views.
   - Files/modules: src/runtime/nodes_common.py (F058), src/runtime/nodes/llm_router.py (F056), src/runtime/tools/bindings/*
   - Complexity/risk: **med**
   - Category: **Mechanical code**

6. **Add a defs↔bindings consistency check test.**
   - Why: Tools are defined twice; a quick unit test can assert name/parameters alignment.
   - Files/modules: src/runtime/tools/definitions/*, src/runtime/tools/bindings/*, src/tests/*
   - Complexity/risk: **low**
   - Category: **Tests/dev tooling**

7. **Prompt-only: tighten router contract to emit only known routes and a clear `need` list.**
   - Why: Routing strings are relied upon by `graph_build`; prompt drift can break routing silently.
   - Files/modules: resources/prompts/runtime_router.txt (F023), src/runtime/graph_build.py (F045)
   - Complexity/risk: **low**
   - Category: **Prompt-only**

8. **Prompt-only: context_builder should output canonical `context.complete`, `context.sources`, and `context.next` fields only.**
   - Why: Reduce schema drift by forcing a minimal JSON contract in the prompt.
   - Files/modules: resources/prompts/runtime_context_builder.txt (F019), src/runtime/nodes/llm_context_builder.py (F052)
   - Complexity/risk: **low**
   - Category: **Prompt-only**

9. **Add a scoped state view mechanism in `nodes_common` (projection + patch).**
   - Why: Supports the strategic direction and reduces accidental coupling to full state.
   - Files/modules: src/runtime/nodes_common.py (F058), src/runtime/state.py (F073), src/runtime/nodes/*
   - Complexity/risk: **high**
   - Category: **LLM-node code + mechanical**

10. **Improve debug state sanitization to remove all non-JSON-serializable fields by type walk.**
   - Why: Runner currently special-cases a few keys; a generic scrubber reduces UI/log breakage.
   - Files/modules: src/runtime/langgraph_runner.py (F049)
   - Complexity/risk: **med**
   - Category: **Mechanical code**

11. **Normalize time context fields: `now_iso`/`timezone` vs `NOW`/`TZ` token names.**
   - Why: Token mismatch has already caused runtime errors; enforce consistent naming.
   - Files/modules: src/runtime/state.py (F073), src/runtime/nodes/*.py, resources/prompts/*.txt
   - Complexity/risk: **med**
   - Category: **Mechanical code**

12. **Add explicit versioning to `world_state.json` schema.**
   - Why: Allows future migrations (Obsidian docs, episodic ledger) without breaking existing state.
   - Files/modules: src/controller/world_state.py (F037), var/llm-thalamus-dev/state/world_state.json (F112)
   - Complexity/risk: **low**
   - Category: **Mechanical code**

13. **Add a `project_status` mechanical compiler stub that reads world/context and writes `var/.../state/project_status.json`.**
   - Why: Creates a concrete integration point and forces schema decisions early.
   - Files/modules: src/controller/worker.py (F036), src/controller/world_state.py (F037), src/runtime/state.py (F073)
   - Complexity/risk: **med**
   - Category: **Mechanical code**

14. **Tool loop: emit tool_call/tool_result events with structured payloads (not only log lines).**
   - Why: UI could render tool traces without parsing logs; helps debugging and deterministic manifests.
   - Files/modules: src/runtime/tool_loop.py (F074), src/runtime/events.py (F044), src/runtime/emitter.py (F042), src/ui/*
   - Complexity/risk: **med**
   - Category: **Mechanical code**

15. **Document node keys vs node IDs and enforce them in code.**
   - Why: Policy uses node keys; nodes use NODE_ID; mixing is easy to get wrong.
   - Files/modules: src/runtime/tools/policy/node_skill_policy.py (F083), src/runtime/nodes/*.py, src/runtime/graph_build.py (F045)
   - Complexity/risk: **low**
   - Category: **Docs + mechanical**

