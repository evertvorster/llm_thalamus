# llm_thalamus Architecture & Codebase Audit (Overview)

## Index (if you split the deliverable)

- `docs/architecture/audit_overview.md` — Sections 0–9, 11–12 (this file)
- `docs/architecture/audit_file_inventory.md` — Section 10 (complete per-file inventory)
- `docs/architecture/audit_appendix.md` — Extra excerpts, schemas, and “unknowns to confirm”

---

## 0) Document Control

- **Snapshot identifier:** provided snapshot (zip sha256 prefix `8cf61fd13cdf`)
- **Date:** 2026-02-27
- **How to use this document:**
  - Start with **Section 3 (Runtime Walkthrough)** and **Section 4 (State/Dataflow)** to understand behavior.
  - Use **Section 6 (Node Catalog)** and **Section 7 (Tooling Catalog)** when changing prompts/tools.
  - Use **Section 10** (separate file) to locate code ownership and risks.
- **Conventions used:**
  - **Node IDs** are the registry IDs (e.g. `llm.router`) registered via `runtime.registry.register()` (see `src/runtime/registry.py`).
  - **Graph node keys** are the LangGraph node names (e.g. `"router"`, `"answer"`) used in `StateGraph.add_node()` (see `src/runtime/graph_build.py`).
  - **State** refers to the JSON-serializable dict-like object `runtime.state.State` (see `src/runtime/state.py`).
  - Prompt placeholders use `<<TOKEN>>` syntax enforced by `runtime.prompting.render_tokens()` (see `src/runtime/prompting.py`).

---

## 1) System Overview

### What the system does today

`llm_thalamus` is a local, GUI-driven LLM orchestrator that:
- Loads a configuration (`resources/config/config.json` by default via `src/config/*`).
- Boots a Qt UI (`src/ui/*`) and runs a per-turn orchestration worker (`src/controller/worker.py`).
- Executes a LangGraph `StateGraph` pipeline (`src/runtime/graph_build.py`) consisting of LLM-backed nodes (`src/runtime/nodes/*`) and a deterministic tool loop (`src/runtime/tool_loop.py`).
- Maintains “durable” world state on disk (`var/.../state/world_state.json`) via controller utilities (`src/controller/world_state.py`) and world-edit tools (`src/runtime/tools/bindings/world_apply_ops.py`).
- Optionally uses an MCP client for OpenMemory access (`src/controller/mcp/*`, invoked through tools `memory_query` / `memory_store`).

### Major subsystems

- **UI layer (Qt):** `src/ui/*` (main window, chat renderer, config dialog, widgets).
- **Controller layer (UI ↔ runtime):** `src/controller/*` (worker, chat history service, world state load/commit, MCP wiring).
- **Runtime/orchestrator:** `src/runtime/langgraph_runner.py`, `src/runtime/graph_build.py`, `src/runtime/state.py`, `src/runtime/events.py`, `src/runtime/emitter.py`.
- **Graph/nodes:** `src/runtime/nodes/*` + `src/runtime/nodes_common.py`.
- **Tooling:** `src/runtime/tool_loop.py`, `src/runtime/tools/*`, `src/runtime/skills/*`.
- **Prompt/resources:** `resources/prompts/*.txt` + loader/utilities.
- **Persistence/data:** `var/.../state/world_state.json`, `var/.../data/chat_history.jsonl`, optional OpenMemory (MCP).

### High-level diagram (conceptual)

```
Qt UI (src/ui/*)
   |
   |  user message
   v
Controller Worker (src/controller/worker.py)
   |
   |  builds deps + runtime services
   v
LangGraph Runner (src/runtime/langgraph_runner.py)
   |
   v
Compiled StateGraph (src/runtime/graph_build.py)
   |
   +--> llm.router (prefill tools mechanically; then structured LLM)
   |        |
   |        +-- tools: chat_history_tail, memory_query
   |
   +--> llm.context_builder (controller node; may call tools)
   |        |
   |        +-- tools: chat_history_tail, memory_query
   |        +-- loops to llm.memory_retriever if requested
   |
   +--> llm.world_modifier (controller node; may call tools)
   |        |
   |        +-- tools: world_apply_ops
   |
   +--> llm.answer (streams assistant text to UI)
   |
   +--> llm.reflect_topics (structured JSON -> updates world.topics)
   |
   +--> llm.memory_writer (structured JSON + tools -> stores memories)
            |
            +-- tools: memory_store
```

---

## 2) Repository Layout

For each top-level directory:

- `.continue/`
  - Purpose: Continue.dev agent configuration and MCP servers/rules.
  - Hotspots: rules that encode workflow expectations for the repo.

- `resources/`
  - Purpose: prompts, default config, documentation templates, and graphics.
  - Hotspots:
    - `resources/prompts/`: prompt templates; **high-leverage** for behavior changes.
    - `resources/config/config.json`: provider/roles/tool limits.

- `src/`
  - Purpose: runtime, controller, and UI implementation.
  - Hotspots:
    - `src/runtime/nodes_common.py`, `src/runtime/tool_loop.py`, `src/runtime/graph_build.py`.

- `var/llm-thalamus-dev/`
  - Purpose: local dev data/state (world state, chat history).

- `.vscode/`
  - Purpose: VSCode workspace settings.

---

## 3) Runtime Walkthrough (end-to-end)

A stepwise narrative from startup to a completed user turn.

### 3.1 Entry point(s) and initialization

1. **Qt app starts** via `src/llm_thalamus.py`:
   - `main()` constructs `QApplication`.
   - Loads config via `config.load.load_config()` (imported as `from config.load import load_config`).
   - Creates `MainWindow(cfg=cfg)` from `src/ui/main_window.py`.
2. **UI wiring**:
   - `MainWindow` owns a worker thread (`controller.worker.Worker`) and the chat renderer.

> Unknown from snapshot: packaging/installation entrypoint (console_script) — no `pyproject.toml`/`setup.py` is present in this snapshot.

### 3.2 Config loading and dependency wiring

The worker constructs:

- **Runtime deps:** `runtime.deps.build_runtime_deps(cfg)`:
  - Loads LLM provider via `runtime.providers.factory.make_provider()`.
  - Validates required role models exist via `provider.list_models()` (fail-fast).
  - Sets prompt root to `<resources_root>/prompts` and enforces `<prompt_name>.txt`.

- **Runtime services:** `controller.runtime_services.build_runtime_services(...)`:
  - Wires `FileChatHistoryService` for `chat_history_tail`.
  - Optionally wires `controller.mcp.client.MCPClient` if OpenMemory URL + API key exist.
  - Builds `runtime.tools.resources.ToolResources` and `runtime.tools.toolkit.RuntimeToolkit`.

### 3.3 Graph build and node sequence

`runtime.langgraph_runner.run_turn_runtime(...)`:

1. Installs a `TurnEmitter` into `state["runtime"]["emitter"]` (see `src/runtime/emitter.py`), plus:
   - `runtime.turn_id`, `runtime.now_iso`, `runtime.timezone`
2. Builds a compiled LangGraph via `runtime.graph_build.build_compiled_graph(deps, services)`.
3. Invokes `compiled.invoke(state)`.

Graph topology (from `src/runtime/graph_build.py`):

- Entry: `"router"`
- Conditional from `"router"` based on `state["task"]["route"]`:
  - `"context_builder"` if route == `"context"`
  - `"world_modifier"` if route == `"world"`
  - else `"answer"`
- Context controller loop:
  - `"context_builder"` → `"memory_retriever"` (if `state["context"]["next"] == "memory_retriever"`) → back to `"context_builder"`
  - `"context_builder"` → `"answer"` (default)
- `"world_modifier"` → `"answer"`
- End-of-turn:
  - `"answer"` → `"reflect_topics"` → `"memory_writer"` → END

### 3.4 Context building and prompt construction

Common mechanics:

- Prompt templates are loaded by `Deps.load_prompt(prompt_name)` from `<prompt_root>/<prompt_name>.txt`.
- Placeholders `<<TOKEN>>` are replaced via `runtime.prompting.render_tokens()`; leftover placeholders raise `RuntimeError("Unresolved prompt tokens: ...")`.

Routing prefill:

- `llm.router` performs **mechanical prefill** by calling:
  - `chat_history_tail(limit=4)`
  - `memory_query(query="<project|topics>", k=6)` if it can derive a query string
- Prefill tool outputs are appended to `state["context"]["sources"]`.

Context builder:

- `llm.context_builder` is a controller node (`run_controller_node`) that may call tools for multiple rounds.
- Tool results are normalized into `state["context"]["sources"]` entries with canonical `kind` values (`chat_turns`, `memories`, etc).

### 3.5 Tool loop behavior and how tool results re-enter the model

Central loop: `runtime.tool_loop.chat_stream(...)`.

- If `tools is None`: direct streaming passthrough.
- If `tools is provided`:
  1. Run tool-capable pass with `response_format=None` (tool calls permitted).
  2. When tool calls exist:
     - Parse/validate args are JSON (`_parse_tool_args_json`).
     - Execute handlers deterministically.
     - Inject `Message(role="tool", name=..., content=<result_json>)` into the model message list.
     - Emit `StreamEvent(type="tool_result")` for UI/diagnostics.
  3. When no more tool calls remain:
     - If `response_format` is configured, do a final formatting pass with tools disabled.

### 3.6 Persistence updates

- **Chat history:** file-backed, via `controller.chat_history_service.FileChatHistoryService` (used by tool `chat_history_tail`).
- **World state:**
  - Loaded via `controller.world_state.load_world_state(path=..., now_iso=..., tz=...)`.
  - Mutated via `world_apply_ops` tool binding (returns updated world JSON).
  - **Commit point is unclear in this snapshot**: `world_apply_ops` does not call `commit_world_state()`.
- **Memories:** via MCP tools:
  - `memory_query` calls MCP tool `openmemory_query`.
  - `memory_store` calls MCP tool `openmemory_store`.

### 3.7 UI/logging events

- Streaming answer uses `TurnEmitter.assistant_delta(...)` (see `runtime.nodes_common.run_streaming_answer_node`).
- Tool invocations/errors are logged via `TurnEmitter.factory.log_line(...)` from the tool loop.
- Node spans (`emitter.span(...)`) track ok/error and may collect “thinking” deltas.

---

## 4) State and Dataflow Model (core of the report)

### 4.1 Identify all “state” objects/dicts

**`runtime.state.State`** (`src/runtime/state.py`) is the LangGraph state container. In practice it’s a dict with these top-level keys:

- `task` (dict): per-turn inputs and routing
  - `task.user_text` (str)
  - `task.route` (str): `"context"` / `"world"` / default
- `world` (dict): durable world mirror
  - `world.topics` (list[str]) updated by `llm.reflect_topics`
  - other keys are defined by `controller.world_state.default_world()`
- `context` (dict): evidence packet / context-builder workspace
  - `context.sources` (list[dict]) evidence items
  - `context.next` (str), `context.complete` (bool)
  - `context.memory_request` (dict) request for memory retriever
- `final` (dict): outputs (currently `final.answer`)
- `runtime` (dict): orchestrator-only transient data
  - `runtime.emitter` (TurnEmitter; non-serializable)
  - `runtime.turn_id`, `runtime.now_iso`, `runtime.timezone`
  - `runtime.issues` (list), `runtime.node_trace` (list[str]), `runtime.status` (str)

### 4.2 Durable world state vs per-turn working state

- **Durable world state:** intended to be `world_state.json` on disk (loaded by controller).
- **Per-turn state:** `task`, `context`, `final`, `runtime`.

### 4.3 Pain points impacting future direction

- **Scoped state views:** no per-node projection; all nodes see the full state dict.
- **`context` schema drift:** some nodes write into `context.sources`, others into `context.context.sources` (nested).
- **World commit boundary unclear:** tools mutate in-memory and return world, but do not commit.
- **MCP identity:** `mcp_openmemory_user_id` appears set to the API key string in `controller.runtime_services.build_runtime_services()`.

---

## 5) Subsystem Deep Dives (module-by-module)

### UI layer

- Responsibilities: render chat, accept input, display streaming updates, show config dialogs.
- Key modules: `src/ui/main_window.py`, `src/ui/chat_renderer.py`, `src/ui/config_dialog.py`, `src/ui/widgets.py`.
- Dependencies: controller worker/services; runtime events/emitter.

### Runtime / orchestrator layer

- Responsibilities: build graph, run turns, install emitter, manage node trace.
- Key modules: `src/runtime/langgraph_runner.py`, `src/runtime/graph_build.py`, `src/runtime/emitter.py`, `src/runtime/events.py`, `src/runtime/state.py`.

### Graph / nodes layer

- Responsibilities: implement node behavior via prompt templates and tool loop wrappers.
- Key modules: `src/runtime/nodes/*`, `src/runtime/nodes_common.py`, `src/runtime/registry.py`.

### Tooling layer

- Responsibilities: tool schemas/handlers, node skill allowlists, deterministic tool execution.
- Key modules: `src/runtime/tool_loop.py`, `src/runtime/tools/*`, `src/runtime/skills/*`.

### Prompt/resources layer

- Responsibilities: prompt files and token rendering.
- Key modules: `resources/prompts/*`, `src/runtime/prompting.py`, `src/runtime/deps.py`.

### Persistence/data layer

- Responsibilities: world state load/commit, chat history, MCP memory.
- Key modules: `src/controller/world_state.py`, `src/controller/chat_history_service.py`, `src/controller/mcp/*`, `src/runtime/tools/bindings/*`.

### Supporting utilities/scripts

- `src/tests/*` are probe scripts and experiments; not structured as unit tests.

---

## 6) Node Catalog (if LangGraph nodes exist)

Enumerated nodes in the active graph (from `src/runtime/graph_build.py`):

- `llm.router` (`src/runtime/nodes/llm_router.py`)
- `llm.context_builder` (`src/runtime/nodes/llm_context_builder.py`)
- `llm.memory_retriever` (`src/runtime/nodes/llm_memory_retriever.py`)
- `llm.world_modifier` (`src/runtime/nodes/llm_world_modifier.py`)
- `llm.answer` (`src/runtime/nodes/llm_answer.py`)
- `llm.reflect_topics` (`src/runtime/nodes/llm_reflect_topics.py`)
- `llm.memory_writer` (`src/runtime/nodes/llm_memory_writer.py`)

(Per-node details are in Section 1 and in the per-file inventory.)

---

## 7) Tooling System Catalog

- **Tool registry:** `RuntimeToolkit` builds per-node toolsets via skills (`src/runtime/tools/toolkit.py`, `src/runtime/skills/*`).
- **Tool loop:** centralized in `src/runtime/tool_loop.py`.
- **Tool result formatting:** tool outputs injected back as `Message(role="tool")` and also normalized into `state["context"]` by nodes.
- **Logging:** tool call trace via emitter; no durable event log sink evident in snapshot.
- **MCP boundaries:** MCP is used only inside tool bindings, not in nodes.

---

## 8) Persistence Catalog

- `world_state.json`:
  - load/repair: `controller.world_state.load_world_state`
  - commit: `controller.world_state.commit_world_state`
  - schema defaults: `controller.world_state.default_world`
- Chat history:
  - file service: `controller.chat_history_service.FileChatHistoryService`
  - sample file: `var/llm-thalamus-dev/data/chat_history.jsonl`
  - exact JSONL schema: unknown from snapshot without reading sample file + service implementation details
- Memory store:
  - OpenMemory MCP client: `controller.mcp.client.MCPClient`
  - tools: `memory_query`, `memory_store`

---

## 9) Dependency & Call Graph Summaries

### Dependency overview by package

- `src/llm_thalamus.py` → `config.*`, `ui.*`
- `src/ui/*` → `controller.*` (+ runtime events/emitter)
- `src/controller/*` → `runtime.*` (+ MCP client)
- `src/runtime/*` → `langgraph.graph`, `runtime.providers/*`, `runtime.tools/*`

### Key call chains

- UI send → `controller.worker.Worker.run_turn(...)` → `runtime.langgraph_runner.run_turn_runtime(...)` → `runtime.graph_build.build_compiled_graph(...)` → nodes
- Tool calls → `runtime.tool_loop.chat_stream(...)` → handler execution → injected tool messages → continued model stream

### Change amplifiers

- `src/runtime/nodes_common.py`
- `src/runtime/tool_loop.py`
- `src/runtime/tools/toolkit.py` and `src/runtime/tools/providers/static_provider.py`
- `src/runtime/graph_build.py`

---

## 11) Strategic Fit Check (forward plan alignment)

### Obsidian document store via MCP

- Plug-in points: add new tool definitions + bindings + skills + policy allowlist.
- Prompt-only: insufficient (needs new tools).
- Primary risk: evidence packet size and normalization.

### MCP isolated behind tool contracts

- Current fit: strong (nodes call tools only; MCP only in bindings).
- Ensure future lint/policy prevents direct MCP imports in nodes.

### Deterministic `project_status` manifest compiled mechanically

- Current: not implemented (only doc references).
- Plug-in: controller post-turn compiler + persisted manifest, or a tool providing the manifest to nodes.
- Risk: current context schema drift.

### Scoped state views / per-node projections

- Current: not implemented.
- Plug-in: wrapper around node invocation in runner or node factory.
- Prompt-only: insufficient for strict isolation.

### Future episodic SQLite ledger (contract-driven)

- Not implemented; implement behind tool contracts to preserve architecture.

---

## 12) Recommendations (incremental)

1. Normalize `context` schema into a single canonical evidence packet (`context.sources`) and update `memory_retriever`/`memory_writer` to stop writing nested `context.context.sources`.
2. Define per-node IO contracts and implement scoped projections/merge in the runner.
3. Fix `mcp_openmemory_user_id` derivation (do not use API key as user id).
4. Make world-state persistence boundary explicit (commit after `world_apply_ops`).
5. Add prompt-token validation tooling (preflight check) to catch unresolved tokens.
6. Refactor `StaticProvider.get()` to a dict-based registry to reduce edit points when adding tools.
7. (Optional) add a durable structured event log sink for spans/tool calls.
8. Deprecate or remove `src/runtime/build.py` if unused (appears to be legacy bootstrap graph).

