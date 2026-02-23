# llm_thalamus Architecture & Codebase Audit (Snapshot)

## Index
- `audit_overview.md` (this file): sections 0–9, 11–12
- `audit_file_inventory.md`: section 10 (complete per-file inventory with F### IDs)
- `audit_appendix.md`: extra reference material (prompt tokens, node/tool tables, file hashes)

---

## 0) Document Control

- **Snapshot identifier:** provided snapshot (`llm_thalamus_2026-02-23.zip`, sha256 `aca4ad64a29b8260f512d101af1bdc7b9d5424458f6e287e9420ec234acc9c14`)
- **Audit date:** 2026-02-23
- **Audience:** maintainers planning architectural changes, prompt tuning, and tool/persistence refactors.
- **How to use this document**
  - Start with **§3 Runtime Walkthrough** and **§4 State & Dataflow Model** to understand how a turn executes.
  - Use **§6 Node Catalog**, **§7 Tooling Catalog**, and **§8 Persistence Catalog** when changing prompts, adding nodes, or moving boundaries.
  - Use **`audit_file_inventory.md`** to quickly locate where a concept lives (via F### + exact paths).

### Conventions used
- **Paths** are repository-relative and exact.
- **Symbols** are exact Python symbol names (classes/functions/constants) when determinable from parsing.
- **Node IDs** refer to `NodeSpec.node_id` values registered in `src/runtime/registry.py`.
- **“node_key”** refers to the string passed to `RuntimeToolkit.toolset_for_node(<node_key>)` (e.g. `"context_builder"`).
- **State** refers to the per-turn LangGraph `State` dict (see `src/runtime/state.py`).
- If something is not visible in this snapshot: **“unknown from snapshot”** + what would confirm it.

---

## 1) System Overview

### What the system does today (as implemented)
- A **PySide6 desktop UI** launches a **controller worker** that:
  - appends the user message to a JSONL chat history file,
  - loads `world_state.json`,
  - builds runtime dependencies (`Deps`) + runtime services (`RuntimeServices`),
  - executes a **LangGraph StateGraph** for the turn,
  - streams **TurnEvent Protocol v1** events back to the UI (thinking + assistant streaming),
  - commits updated world state back to disk.

### Major subsystems
- **UI layer** (`src/ui/*`): Qt widgets, markdown rendering, log panes, config dialogs.
- **Controller layer** (`src/controller/*`): owns UI-facing persistence (chat history + world state), wires runtime services, runs turns.
- **Runtime / orchestrator** (`src/runtime/*`): LangGraph graph build, node registry, node implementations, provider abstraction, deterministic tool loop, event streaming.
- **Tooling subsystem** (`src/runtime/tools/*`, `src/runtime/skills/*`): code-level capability firewall (node→skill allowlist), tool definitions + deterministic handlers, MCP bridge.
- **Resources** (`resources/*`): prompt templates, config template, graphics.
- **Tests / probes** (`src/tests/*`): LangChain/LangGraph probes and local interactive experiments.
- **Dev data** (`var/llm-thalamus-dev/*`): sample runtime data (JSONL history, SQLite DBs, world state).

### High-level diagram
```text
+----------------------------+
|        PySide6 UI          |
|  src/ui/* + MainWindow     |
+-------------+--------------+
              |
              | Qt signals/slots
              v
+----------------------------+
|   ControllerWorker (Qt)    |
|  src/controller/worker.py  |
|  - chat history JSONL      |
|  - world_state.json        |
+-------------+--------------+
              |
              | builds per-turn State + Deps + Services
              v
+----------------------------+
|  Runtime (LangGraph)       |
|  src/runtime/*             |
|  - build_compiled_graph    |
|  - nodes (LLM)             |
|  - tool_loop (deterministic)|
|  - event streaming (TurnEvent v1)|
+-------------+--------------+
              |
              | tools via RuntimeToolkit (skill allowlist)
              v
+----------------------------+
| Tools / Skills             |
|  src/runtime/tools/*       |
|  - world_apply_ops -> JSON |
|  - memory_query/store -> MCP OpenMemory
|  - chat_history_tail       |
+-------------+--------------+
              |
              v
+----------------------------+
| Persistence                |
|  - controller/world_state  |
|  - controller/chat_history |
|  - var/* (dev data)        |
+----------------------------+
```

---

## 2) Repository Layout

> Note: this audit covers the contents of the provided snapshot zip. Dotfiles shown in your `tree` output (e.g. `.continue`, `.vscode`, `.gitignore`) are **not present in this snapshot**.

### Top-level
- `README.md`, `CONTRIBUTING.md`, `LICENSE.md`
- `Makefile`, `llm_thalamus.desktop`
- `thinking-manual-*.log` (captured logs; appear to be local artifacts)

### `resources/`
- **Purpose:** non-code assets and templates.
- Contents:
  - `resources/config/config.json` (template config)
  - `resources/prompts/*.txt` (per-node prompt templates)
  - `resources/graphics/*` (UI images/icons)
  - `resources/Documentation/*` (templates for authors)

**Hotspots**
- `resources/prompts/*` strongly couples to node token rendering (`src/runtime/prompting.py`) and node prompt mappings (constants like `PROMPT_NAME` in node files).

### `src/`
- **Purpose:** main application code.
- Major packages:
  - `src/config/*`: config bootstrap, schema projection, dev/installed root policies.
  - `src/controller/*`: UI-facing persistence + runtime wiring.
  - `src/runtime/*`: graph, nodes, providers, tools, events.
  - `src/ui/*`: Qt UI implementation.
  - `src/tests/*`: probe scripts (not unit tests in the strict sense).

**Hotspots**
- `src/controller/worker.py`: owns end-to-end turn execution from the UI.
- `src/runtime/graph_build.py`: defines node sequence and branching.
- `src/runtime/tool_loop.py`: deterministic tool loop contract.
- `src/runtime/tools/*` + `src/runtime/skills/*`: capability firewall and MCP boundary.

### `var/`
- **Purpose:** dev runtime state and data (appears to be checked in to snapshot).
- Contents:
  - `var/llm-thalamus-dev/state/world_state.json`
  - `var/llm-thalamus-dev/data/chat_history.jsonl`
  - `var/llm-thalamus-dev/data/*.sqlite`

**Risk:** committing `var/` into releases can leak personal data and causes non-deterministic diffs.

---

## 3) Runtime Walkthrough (end-to-end)

### Entry point(s) and initialization
1. `src/llm_thalamus.py:main(argv)`:
   - calls `config.bootstrap_config(argv)` to produce a `config.ConfigSnapshot`.
   - constructs `QApplication`.
   - constructs `controller.worker.ControllerWorker(cfg)`.
   - constructs `ui.main_window.MainWindow(cfg, controller)` and shows UI.

2. `controller.worker.ControllerWorker.__init__(cfg)`:
   - resolves history + world state paths (`_compute_world_state_path()`).
   - loads world state via `controller.world_state.load_world_state(...)`.
   - builds runtime services via `controller.runtime_services.build_runtime_services(...)`:
     - creates `FileChatHistoryService`
     - optionally wires MCP OpenMemory client (`controller.mcp.client.MCPClient`)
     - creates `ToolResources` + `RuntimeToolkit` + `RuntimeServices`

### Stepwise turn execution narrative
**Triggered by UI:** `ControllerWorker.submit_message(text)` (Qt slot).
1. Writes user message to JSONL history via `controller.chat_history.append_turn(...)`.
2. Builds runtime dependencies: `runtime.deps.build_runtime_deps(cfg)`:
   - creates provider via `runtime.providers.factory.make_provider(...)`
   - validates required models exist via `Deps._validate_required_models_or_die(...)`
   - constructs `Deps` holding provider + per-role model specs.
3. Creates per-turn state: `runtime.state.new_runtime_state(user_text=text)`.
4. Injects controller-owned world into state: `state["world"] = dict(self._world)`.
5. Runs the LangGraph turn with streaming:
   - iterates `runtime.langgraph_runner.run_turn_runtime(state, deps, runtime_services)`
   - forwards TurnEvents to UI signals (`thinking_delta`, `assistant_stream_delta`, `log_line`, etc.)
6. On `world_commit` event, records `final_world`.
7. After graph completion:
   - commits `final_world` to disk via `controller.world_state.commit_world_state(...)`
   - appends assistant message to JSONL history.

### Graph build and node sequence
- Graph compiled per-turn via `runtime.graph_build.build_compiled_graph(deps, services)`.
- Node sequence / branching (exact code path in `src/runtime/graph_build.py`):
  1. Entry: `"router"`
  2. Conditional:
     - if `state["task"]["route"] == "context"` → `"context_builder"` → `"memory_retriever"` → `"answer"`
     - if `state["task"]["route"] == "world"` → `"world_modifier"` → `"answer"`
     - else → `"answer"`
  3. Tail: `"answer"` → `"reflect_topics"` → `"memory_writer"` → END

### Context building and prompt construction
- Node prompts are file-backed:
  - Nodes call `Deps.load_prompt(PROMPT_NAME)` where `PROMPT_NAME` is a constant like `"runtime_router"`.
  - Template tokens like `<<USER_MESSAGE>>` are rendered by `runtime.prompting.render_tokens(...)`.
  - Unresolved tokens raise a hard error (`RuntimeError`), which fails the node.

### Tool loop behavior and tool result reinjection
- Nodes that allow tools call `runtime.tool_loop.chat_stream(...)` with a `ToolSet`:
  - The `ToolSet` is assembled by `RuntimeToolkit.toolset_for_node(node_key)` (see §7).
- Tool loop is deterministic streaming-only:
  - During tool-enabled rounds it sets `response_format=None` (allows tool calls).
  - If no tool calls occur and a `response_format` is desired, it runs a **final formatting pass** with tools disabled.
  - Tool results are appended back into the chat as `Message(role="tool", name=..., tool_call_id=..., content=...)`.

### Persistence updates
- **Chat history:** appended by controller before and after the runtime turn (`append_turn`).
- **World state:**
  - May be mutated inside the turn by the `world_apply_ops` tool handler (writes `world_state.json` immediately).
  - The controller then writes `final_world` again after the turn (potential double-write; see §8 risks).
- **Memory / OpenMemory:** tool handlers call MCP (`openmemory_query`, `openmemory_store`) via `controller.mcp.client.MCPClient` (see §7 and §8).

### UI/logging events
- Runtime produces **TurnEvent Protocol v1** events (`src/runtime/events.py`).
- `ControllerWorker` converts them into Qt signals:
  - thinking stream: `thinking_started`, `thinking_delta`, `thinking_finished`
  - assistant stream: `assistant_stream_start/delta/end`
  - combined logs: `log_line`
  - world refresh: `world_committed`

#### Textual sequence diagram (single turn)
```text
UI(MainWindow)
  -> ControllerWorker.submit_message(user_text)
     -> append_turn(human)
     -> build_runtime_deps(cfg)
     -> new_runtime_state(user_text)
     -> state["world"] = controller_world
     -> run_turn_runtime(state, deps, services)
        -> build_compiled_graph(deps, services)
        -> emitter.start_turn(...)
        -> compiled.invoke(state) [in background thread]
           -> router
           -> (context_builder -> memory_retriever) OR (world_modifier) OR answer
           -> answer -> reflect_topics -> memory_writer
        -> emit world_commit(delta)
        -> emit turn_end(ok|error)
     -> append_turn(assistant) [on assistant_end]
     -> commit_world_state(final_world) [after loop]
```

---

## 4) State and Dataflow Model (core)

### Primary per-turn state container
- **Type:** `runtime.state.State` is an alias `dict[str, Any]`.
- **Constructor:** `runtime.state.new_runtime_state(user_text: str) -> State`.

#### Top-level keys in `State` (current shape)
- `task`: user request and routing metadata.
- `runtime`: trace, status, issues, time context, and **injected emitter**.
- `context`: aggregated context object built by context nodes.
- `final`: answer text.
- `world`: durable world state snapshot (but handled as a dict, not a typed schema).

> The TypedDicts in `src/runtime/state.py` describe intended shape, but runtime code is permissive and uses `.get()` and `.setdefault()` widely.

### State structures, ownership, and mutation

#### `state["task"]` (`RuntimeTask`)
- **Created:** `new_runtime_state(...)`.
- **Mutated by:**
  - `llm.router` sets:
    - `task.language`
    - `task.route` (critical for branching) in `src/runtime/nodes/llm_router.py`.
- **Read by:** most nodes (prompt inputs).
- **Key fields:**
  - `user_text` (authoritative user message for the turn)
  - `language` (router-selected)
  - `route` (router-selected: `"context" | "world" | "answer"`)

#### `state["runtime"]` (`RuntimeRuntime`)
- **Created:** `new_runtime_state(...)`.
- **Mutated by:**
  - every node appends to `runtime.node_trace`.
  - router writes `runtime.status`.
  - context builder merges per-round issues/context and may write log lines.
  - `run_turn_runtime` injects `runtime.emitter` (non-JSON, runtime-only object).
- **Key fields:**
  - `node_trace`: append-only list of node IDs visited.
  - `status`: router-provided status string (also consumed by answer prompt).
  - `issues`: append-only list intended for answer node.
  - `now_iso`, `timezone`: declared in type, but **population is unclear** in this snapshot:
    - Some prompts expect them, but the code path that sets them is **unknown from snapshot** unless done in a node (see §8 + §11).

**Risk:** `runtime.emitter` makes State non-serializable. This is fine for in-memory LangGraph execution, but blocks any “checkpointing” unless stripped.

#### `state["context"]` (`RuntimeContext`)
- **Created:** empty dict in `new_runtime_state`.
- **Mutated by:**
  - `llm.context_builder`: merges incremental context objects across multiple rounds (`MAX_CONTEXT_ROUNDS`).
  - `llm.memory_retriever`: augments/merges memory results into context (exact keys depend on prompt output).
- **Key fields:** not strongly enforced; prompt-driven JSON contract.

**Risk:** context schema is emergent and prompt-controlled; any downstream usage should validate.

#### `state["final"]` (`RuntimeFinal`)
- **Created:** `{ "answer": "" }` in `new_runtime_state`.
- **Mutated by:** `llm.answer` sets `final.answer`.
- **Read by:** `llm.reflect_topics`, `llm.memory_writer`.

#### `state["world"]` (durable world snapshot)
- **Created:** injected by controller: `state["world"] = dict(self._world)` in `ControllerWorker._handle_message`.
- **Mutated by:**
  - **Inside-turn tools**: `world_apply_ops` loads + commits `world_state.json` and returns the updated world; node prompt logic may incorporate it.
  - **End-of-turn**: `run_turn_runtime` emits a `world_commit` event derived from comparing input `state["world"]` and output `out["world"]`. The controller then commits `final_world`.

**Pain points for scoped views**
- Nodes currently receive a full `WORLD_JSON` dump in prompts.
- There is no mechanical projection layer (e.g., “node sees only identity + topics”)—token budget and information-hazard risks.

**Pain points for deterministic `project_status`**
- World state is a free-form dict with lists (`topics`, `goals`, `rules`) and `project` string.
- There is no separate compiled manifest (no `project_status` file in snapshot), so any status must be inferred/prompted.

**Pain points for tool contract boundaries**
- Nodes don’t call MCP directly (good), but tool wiring passes a full `MCPClient` into `ToolResources`.
- Some values look incorrect/unsafe:
  - `mcp_openmemory_user_id` is derived from `mcp_openmemory_api_key` in `build_runtime_services` (likely a bug; see §8).

---

## 5) Subsystem Deep Dives (module-by-module)

### 5.1 UI layer (`src/ui/*`)
**Responsibilities**
- Display chat, thinking stream, combined logs, and a world summary.
- Provide config dialogs (model picker) and send user messages to controller.

**Key modules**
- `src/ui/main_window.py`: `MainWindow` ties widgets to `ControllerWorker` signals/slots.
- `src/ui/widgets.py`: core widgets (chat input, log windows, brain indicator, world summary).
- `src/ui/chat_renderer.py`: markdown/code fence rendering to HTML (`ChatRenderer`, `render_chat_html`).

**Dependencies**
- Imports `controller.worker.ControllerWorker` from `src/controller/worker.py`.
- Consumes `ControllerWorker` Qt signals: `assistant_stream_*`, `thinking_*`, `log_line`, `world_committed`, `history_turn`.

**Coupling/hotspots**
- UI expects specific event shapes and emits lines based on `TurnEvent.payload`.
- World summary UI depends on the disk file path `ControllerWorker.world_state_path`.

### 5.2 Controller / orchestrator layer (`src/controller/*`)
**Responsibilities**
- Own persistent chat history and disk world state.
- Wire runtime services (tools/resources) and execute LangGraph turns.
- Translate TurnEvents into UI signals.

**Key modules**
- `src/controller/worker.py`: `ControllerWorker` (central orchestrator).
- `src/controller/chat_history.py`: JSONL append/read helpers.
- `src/controller/chat_history_service.py`: `FileChatHistoryService` used by tools.
- `src/controller/world_state.py`: load/commit `world_state.json`.
- `src/controller/runtime_services.py`: builds `RuntimeServices` + `ToolResources` + MCP.

**Hotspots**
- `ControllerWorker._handle_message` mixes responsibilities:
  - persistence writes,
  - runtime execution,
  - UI signal emission,
  - world commit logic.
  This is acceptable for a small app but is a change amplifier.

### 5.3 Runtime / graph / nodes layer (`src/runtime/*`)
**Responsibilities**
- Define the per-turn LangGraph and its nodes.
- Provide provider abstraction + deterministic streaming tool loop.
- Emit streaming TurnEvents.

**Key modules**
- Graph build: `src/runtime/graph_build.py`
- Node registry: `src/runtime/registry.py`
- Nodes: `src/runtime/nodes/*.py`
- Provider abstraction: `src/runtime/providers/*`
- Tool loop: `src/runtime/tool_loop.py`
- Events + streaming infra: `src/runtime/events.py`, `src/runtime/emitter.py`, `src/runtime/event_bus.py`, `src/runtime/langgraph_runner.py`
- Prompt rendering: `src/runtime/prompting.py`

**Coupling/hotspots**
- Nodes import `render_tokens` and are tightly coupled to prompt token names.
- Nodes rely on streaming provider semantics (`StreamEvent` types); any provider change must preserve the contract.

### 5.4 Tooling layer (`src/runtime/tools/*`, `src/runtime/skills/*`)
**Responsibilities**
- Provide curated, deterministic tool sets per node (capability firewall).
- Define tool schemas and bind implementations to resources.
- Bridge to MCP OpenMemory.

**Key modules**
- Capability policy: `src/runtime/tools/policy/node_skill_policy.py`
- Skill enablement: `src/runtime/skills/registry.py`
- Tool assembly: `src/runtime/tools/toolkit.py` (`RuntimeToolkit.toolset_for_node`)
- Tool definitions: `src/runtime/tools/definitions/*.py`
- Tool bindings: `src/runtime/tools/bindings/*.py`
- Static provider: `src/runtime/tools/providers/static_provider.py`

**Coupling/hotspots**
- Node tool access is keyed by *node_key strings* (not Node IDs), so renaming nodes requires coordinated changes.
- MCP is currently “just another tool binding,” but the MCP client is created in controller code (not runtime).

### 5.5 Prompt/resources layer (`resources/prompts/*`, `src/runtime/prompting.py`)
**Responsibilities**
- Store per-node templates.
- Enforce token completeness (`render_tokens` fails on unresolved placeholders).

**Hotspots**
- Token drift between prompt files and node code is a failure mode (hard errors).

### 5.6 Persistence/data layer (`src/controller/*`, `var/*`)
**Responsibilities**
- Disk world state and chat history.
- MCP OpenMemory for semantic memory.
- Dev artifacts (`var/*.sqlite`) included in snapshot.

**Known coupling**
- Tools directly import `controller.world_state` for world mutation.
- Chat history tool uses `FileChatHistoryService`.

### 5.7 Supporting utilities/scripts (`src/tests/*`, top-level logs)
**Responsibilities**
- Experiments/probes (LangChain parsers, router tests, interactive Ollama chat).
- Not structured as CI-run unit tests.

**Risk**
- Probe scripts can rot and obscure what’s “production” vs “experimental”.

---

## 6) Node Catalog (LangGraph nodes)

> Nodes are registered via `runtime.registry.register(NodeSpec(...))` at import time in `src/runtime/nodes/*.py` and are wired into the graph in `src/runtime/graph_build.py`.

### Node list (graph order)
- `llm.router` → conditional
- `llm.context_builder` → `llm.memory_retriever` → `llm.answer`
- `llm.world_modifier` → `llm.answer`
- `llm.answer` → `llm.reflect_topics` → `llm.memory_writer`

### Per-node details (as implemented)

#### `llm.router` (`src/runtime/nodes/llm_router.py`)
- **Purpose:** choose route (`context`|`world`|default answer), choose language, emit status.
- **Role/model:** role `"router"` (`Deps.get_llm("router")`).
- **Prompt:** `resources/prompts/runtime_router.txt`
  - tokens: NOW, TZ, USER_MESSAGE, WORLD_JSON
- **Reads state:** `task.user_text`, `world.now`, `world.tz`, `world` (full JSON).
- **Writes state:** `task.language`, `task.route`, `runtime.status`.
- **Tools:** disabled (`tools=None`).

#### `llm.context_builder` (`src/runtime/nodes/llm_context_builder.py`)
- **Purpose:** iteratively build a structured `context` object using tools (multi-round).
- **Role/model:** role `"planner"` (`ROLE_KEY = "planner"`).
- **Prompt:** `resources/prompts/runtime_context_builder.txt`
  - tokens: EXISTING_CONTEXT_JSON, USER_MESSAGE, WORLD_JSON
- **Reads state:** `task.user_text`, `world`, existing `context`.
- **Writes state:** `context` (merged), may add `runtime.issues` via merged outputs (prompt-driven).
- **Tools:** enabled via `services.tools.toolset_for_node("context_builder")`.
  - Allowed skills (policy): `NODE_ALLOWED_SKILLS["context_builder"] == {"core_context","mcp_memory_read"}`.

#### `llm.memory_retriever` (`src/runtime/nodes/llm_memory_retriever.py`)
- **Purpose:** query memory store based on current task/world/topics and merge results into context.
- **Role/model:** role `"reflect"` (per `ROLE_KEY` in the file).
- **Prompt:** `resources/prompts/runtime_memory_retriever.txt`
  - tokens: CONTEXT_JSON, NODE_ID, NOW_ISO, REQUESTED_LIMIT, ROLE_KEY, TIMEZONE, TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- **Tools:** enabled via `toolset_for_node("memory_retriever")`
  - Allowed skills: `{"mcp_memory_read"}`.

#### `llm.world_modifier` (`src/runtime/nodes/llm_world_modifier.py`)
- **Purpose:** propose/execute world state edits (via tools), then update `state["world"]` (prompt-driven).
- **Role/model:** role `"planner"`.
- **Prompt:** `resources/prompts/runtime_world_modifier.txt`
  - tokens: USER_MESSAGE, WORLD_JSON
- **Tools:** enabled via `toolset_for_node("world_modifier")`
  - Allowed skills: `{"core_world"}` (i.e., world ops tool(s)).

#### `llm.answer` (`src/runtime/nodes/llm_answer.py`)
- **Purpose:** generate the assistant message; emits `assistant_*` TurnEvents for streaming chat bubble.
- **Role/model:** role `"answer"`.
- **Prompt:** `resources/prompts/runtime_answer.txt`
  - tokens: CONTEXT_JSON, ISSUES_JSON, NOW_ISO, STATUS, TIMEZONE, USER_MESSAGE, WORLD_JSON
- **Reads state:** `task`, `world`, `context`, `runtime.status`, `runtime.issues`.
- **Writes state:** `final.answer`.
- **Tools:** disabled.

#### `llm.reflect_topics` (`src/runtime/nodes/llm_reflect_topics.py`)
- **Purpose:** update `world.topics` (and possibly other world fields) by reflection.
- **Role/model:** role `"reflect"`.
- **Prompt:** `resources/prompts/runtime_reflect_topics.txt`
  - tokens: ASSISTANT_MESSAGE, PREV_TOPICS_JSON, USER_MESSAGE, WORLD_JSON
- **Tools:** disabled (reflection is prompt-driven only).

#### `llm.memory_writer` (`src/runtime/nodes/llm_memory_writer.py`)
- **Purpose:** decide what to store as memory (OpenMemory) based on turn context and answer.
- **Role/model:** role `"reflect"` (per file).
- **Prompt:** `resources/prompts/runtime_memory_writer.txt`
  - tokens: ASSISTANT_ANSWER, CONTEXT_JSON, NODE_ID, NOW_ISO, ROLE_KEY, TIMEZONE, USER_MESSAGE, WORLD_JSON
- **Tools:** enabled via `toolset_for_node("memory_writer")`
  - Allowed skills: `{"mcp_memory_write"}`.

---

## 7) Tooling System Catalog

### Tool registry / discovery
- **ToolSet assembly point:** `RuntimeToolkit.toolset_for_node(node_key)` in `src/runtime/tools/toolkit.py`.
- **Capability firewall:**
  - Enabled skills: `src/runtime/skills/registry.py:ENABLED_SKILLS`
  - Node→skills allowlist: `src/runtime/tools/policy/node_skill_policy.py:NODE_ALLOWED_SKILLS`
- **Tool provider implementation:** `src/runtime/tools/providers/static_provider.py` (binds known tool names to definitions+handlers).

### Tool declarations
- Tool schemas are defined in `src/runtime/tools/definitions/*.py`.
- Handlers are bound in `src/runtime/tools/bindings/*.py` against a `ToolResources` instance.

### Tool loop
- Implemented in `src/runtime/tool_loop.py:chat_stream(...)`.
- Key behaviors:
  - Streaming-only; the loop yields provider stream events through to the node.
  - Tool rounds run with `response_format=None` to permit tool calls.
  - Optional final formatting pass enforces response format and disables tools.
  - Tool args JSON is validated (`_parse_tool_args_json`) and tool errors are returned as JSON error objects rather than failing the turn.

### Tool result formatting + injection
- Tool handler returns a **string** (typically JSON text).
- Tool loop appends it as `Message(role="tool", name=..., tool_call_id=..., content=result_text)`.
- Tool loop also yields `StreamEvent(type="tool_result", text=result_text)` for diagnostics.

### Logging
- Tool calls and tool errors are emitted as `log_line` events when an emitter is provided:
  - logger: `"tool_loop"`
  - message: `"[tool] call {name} args=..."`
- Missing / limited:
  - there is no explicit “tool_result” log line (only StreamEvent), unless nodes surface it.

### MCP usage and boundaries
- MCP appears only in tool bindings (good boundary):
  - `src/runtime/tools/bindings/memory_query.py`
  - `src/runtime/tools/bindings/memory_store.py`
- MCP client is created in controller (`src/controller/runtime_services.py`) and injected via `ToolResources.mcp`.

**Unknown from snapshot**
- Whether MCP supports multiple servers beyond OpenMemory is partially implied (`MCPClient(servers=...)`) but not confirmed without reading transport details (§10 has exact file inventory).

---

## 8) Persistence Catalog

### `world_state.json`
- **Disk location:** controller computes path; in dev data it is `var/llm-thalamus-dev/state/world_state.json`.
- **Load/save:** `src/controller/world_state.py`
  - `default_world(...)` produces base schema:
    - `updated_at`, `project`, `topics`, `goals`, `rules`, `identity` fields (+ optional `tz`)
  - `load_world_state(path, now_iso, tz)`:
    - creates file if missing,
    - resets to defaults if JSON corrupt,
    - refreshes `updated_at` on load when `now_iso` provided.
  - `commit_world_state(path, world)` writes via temp file replace.

**Mutation points**
- End-of-turn commit by controller (`ControllerWorker._handle_message`).
- In-turn mutations by tool handler:
  - `src/runtime/tools/bindings/world_apply_ops.py` loads and commits world state directly.

**Risks**
- **Double-write / conflict risk:** `world_apply_ops` commits during the turn, then controller commits `final_world` after the turn. If `final_world` was derived from an earlier snapshot (or if a node never refreshed `state["world"]`), the final commit could overwrite changes. Confirm behavior in `llm_world_modifier.py` (it should update `state["world"]` from tool results).
- **Schema drift:** world is a free-form dict; no mechanical schema enforcement beyond defaults.

### Chat history (`chat_history.jsonl`)
- **Disk location:** configured via config; dev example is `var/llm-thalamus-dev/data/chat_history.jsonl`.
- **Write/read:** `src/controller/chat_history.py`
  - `append_turn(...)` appends with max trimming
  - `read_tail(...)` reads last N turns
- Used by tool `chat_history_tail` (see tools bindings/definitions).

### Memory / episode stores
- The snapshot includes:
  - `var/llm-thalamus-dev/data/memory.sqlite`
  - `var/llm-thalamus-dev/data/episodes.sqlite`
- **Unknown from snapshot:** whether production runtime reads these SQLite files.
  - Code paths in runtime tools primarily use MCP OpenMemory, not local sqlite.
  - Confirm by searching for `sqlite3` usage (see appendix).

### MCP OpenMemory persistence
- `memory_query` and `memory_store` call MCP tools:
  - `"openmemory_query"`, `"openmemory_store"`
- `ToolResources.mcp_openmemory_user_id` is set from `mcp_openmemory_api_key` in `build_runtime_services`:
  - **Likely a bug / security smell** (user_id should not be API key).
  - Confirm intended schema in `resources/config/config.json`.

### Logs and caches
- TurnEvent logs are streamed, but **on-disk logging** is unclear:
  - config includes `log_file`, but this snapshot does not show a runtime logger writing there (unknown without UI code review; see §10).
- `thinking-manual-*.log` are present as artifacts, but not referenced by code (likely manual runs).

---

## 9) Dependency & Call Graph Summaries

### Package-level dependency overview (internal Python modules)
- `llm_thalamus` (entrypoint) depends on:
  - `config`
  - `controller.worker`
  - `ui.main_window`
- `controller.*` depends on:
  - `runtime.*` (Deps, runner, state)
  - `controller.mcp.*` (optional)
- `runtime.*` depends on:
  - `langgraph` (graph execution)
  - provider-specific deps (e.g. requests for Ollama) (exact in `src/runtime/providers/*`)
- `runtime.tools.*` depends on:
  - `controller.world_state` (world mutation)
  - `controller.chat_history_service` (history tool)
  - `controller.mcp.client` (OpenMemory tools)

### Key call chains (most important)
1. **UI boot**
   - `src/llm_thalamus.py:main` → `config.bootstrap_config` → `ControllerWorker(cfg)` → `MainWindow(cfg, controller)`
2. **Turn execution**
   - `ControllerWorker.submit_message` → `_handle_message` → `build_runtime_deps` → `new_runtime_state` → `run_turn_runtime`
3. **Graph execution**
   - `run_turn_runtime` → `build_compiled_graph` → node callables produced by `NodeSpec.make(...)`
4. **Tool invocation**
   - node → `runtime.tool_loop.chat_stream` → provider stream → tool_call capture → handler dispatch (`RuntimeToolkit`)

### Change amplifiers (high ripple areas)
- `src/controller/worker.py` (orchestrator + persistence + UI signal glue).
- `src/runtime/tool_loop.py` (provider contract + tool injection).
- `src/runtime/providers/types.py` (central type contract for provider/tool loop).
- `resources/prompts/*` (token contracts; failures break nodes).
- `src/runtime/tools/toolkit.py` + `node_skill_policy.py` (capability firewall; node renames ripple).

---

## 11) Strategic Fit Check (forward plan alignment)

### Goal A: Obsidian document store via MCP (preferred over MCP as a general substrate)
**Where it would plug in**
- New MCP tools should appear as **tool definitions + bindings**, then be added to a new or existing **skill**:
  - add in `src/runtime/tools/definitions/`
  - bind in `src/runtime/tools/bindings/`
  - expose via a new skill in `src/runtime/skills/catalog/` and `src/runtime/tools/toolkit.py:_load_skills()`

**Refactoring likely needed**
- `ToolResources` needs a place for an “Obsidian vault path” or an MCP server config distinct from OpenMemory.
- Consider separating MCP server configs by purpose: `openmemory`, `obsidian`, etc. (today `DEFAULT_OPENMEMORY_SERVER_ID = "openmemory"` is hard-coded in bindings).

**Prompt-only opportunities**
- Context builder prompt could be tuned to request Obsidian search tool usage once it exists.
- Router prompt could route to `"context"` more aggressively for doc-heavy tasks.

**Risks**
- Token budget if full documents are shoved into `WORLD_JSON`/context; prefer tool-based retrieval.

### Goal B: MCP isolated behind tool contracts; nodes never call MCP directly
**Current state:** already aligned.
- Nodes do not import MCP modules.
- MCP is only reachable via `ToolResources.mcp` and tool handlers.

**Risks**
- Tool handlers import `controller.world_state` directly, which is acceptable but makes “runtime-only” extraction harder.
- Ensure future MCP additions are similarly only exposed via tool bindings.

### Goal C: Deterministic `project_status` manifest compiled mechanically
**Where it would plug in**
- Best fit: a mechanical step in controller or a non-LLM runtime node that:
  - reads world state + episodes + other durable stores,
  - writes a deterministic manifest file (e.g., `var/.../project_status.json` or `state/project_status.json`).
- Candidate modules:
  - `src/controller/world_state.py` (world I/O)
  - a new `src/controller/project_status.py` (mechanical compiler)
  - optionally a new runtime node that calls no LLM/tools and only updates state.

**Likely refactors**
- Define a stable schema for `project_status` separate from `world_state`.
- Add update policy: who can mutate it, how diffs are computed, and when to regenerate.

**Prompt-only**
- None for determinism; compilation must be mechanical.

### Goal D: Scoped state views so nodes only see what they need
**Where it would plug in**
- Add a mechanical projection layer before prompt rendering (best):
  - e.g., `runtime/scoped_state.py` (new) to create per-node views:
    - `world_view_for(node_id)` and `context_view_for(node_id)`
- Update nodes to render `WORLD_JSON` from view instead of raw `state["world"]`.

**Likely refactors**
- Nodes currently call `json.dumps(state.get("world", {}))` directly.
- Introduce a central helper in runtime (or services) so view logic is not duplicated across nodes.

**Prompt-only**
- Partial: you can ask nodes to “ignore irrelevant fields,” but they still receive them. True scoping requires mechanical changes.

### Goal E: Prefer prompt tuning over code when feasible
**Where it fits today**
- Prompts are already first-class (`resources/prompts/*.txt`), and nodes use `render_tokens`.
- Many behaviors (context schema, memory write selection, topic reflection) are prompt-driven.

**Low-code prompt tuning candidates**
- Router accuracy (route selection, language selection): `resources/prompts/runtime_router.txt`
- Context builder merge semantics (how to declare `complete`, `issues`, `sources`): `resources/prompts/runtime_context_builder.txt`
- Memory writer dedupe guidance (store only new facts): `resources/prompts/runtime_memory_writer.txt` + strengthen tool feedback format.

---

## 12) Recommendations (incremental)

Prioritized (higher = earlier), with type classification.

1. **Fix `mcp_openmemory_user_id` derivation (likely uses API key today).**
   - Why: current wiring appears to treat API key as a user/tenant id → data leakage risk + incorrect tenancy.
   - Touch: `src/controller/runtime_services.py` (and config schema if needed).
   - Complexity: low. Type: mechanical code.

2. **Eliminate world double-write hazards by making world mutation single-source-of-truth.**
   - Option: forbid `world_apply_ops` from committing to disk; instead return ops and let controller commit once.
   - Or: ensure `llm_world_modifier` always updates `state["world"]` from tool result before turn end.
   - Touch: `src/runtime/tools/bindings/world_apply_ops.py`, `src/controller/worker.py`, `src/runtime/nodes/llm_world_modifier.py`.
   - Complexity: med. Type: mechanical code.

3. **Introduce mechanical scoped views (`WORLD_JSON_VIEW`) and remove raw world dumps from prompts.**
   - Why: supports scoped state views and reduces prompt leakage/cost.
   - Touch: new `src/runtime/scoping.py` (or similar) + all node files that render `WORLD_JSON`.
   - Complexity: med. Type: mechanical code.

4. **Add a deterministic `project_status` compiler module and output file (no LLM).**
   - Why: aligns with strategic direction; reduces prompt reliance for “status”.
   - Touch: new `src/controller/project_status.py` + controller worker integration.
   - Complexity: med/high. Type: mechanical code.

5. **Harden node/tool naming: unify `node_id` vs `node_key`.**
   - Why: tool access is keyed by `"context_builder"` strings; renames are risky.
   - Touch: `src/runtime/tools/policy/node_skill_policy.py`, nodes calling `toolset_for_node(...)`.
   - Complexity: low/med. Type: mechanical code.

6. **Clarify and centralize time context (`now_iso`, `timezone`) population.**
   - Why: prompts expect `NOW_ISO` / `TIMEZONE`, but ownership is unclear.
   - Touch: `ControllerWorker._handle_message` to set `state["runtime"]["now_iso"]` and `["timezone"]`, and/or create a mechanical runtime node.
   - Complexity: low. Type: mechanical code (or prompt-only if you remove tokens, but better to wire properly).

7. **Split `ControllerWorker` responsibilities (optional, if it becomes a bottleneck).**
   - Extract runtime execution into a pure service class with no Qt.
   - Complexity: med. Type: mechanical code.

8. **Packaging alignment: Makefile/Desktop entrypoints don’t match the `src/` layout in this snapshot.**
   - Why: installed mode may be broken or stale.
   - Touch: `Makefile`, `llm_thalamus.desktop`, possibly add real entrypoints.
   - Complexity: med. Type: mechanical code.

9. **Convert `src/tests/*` into a clear “probes/” area or add minimal pytest harness.**
   - Why: reduce ambiguity about what is supported.
   - Complexity: low/med. Type: mechanical code.

10. **Prompt-only: tighten memory writer dedupe + “don’t store if semantically similar” rules.**
   - Touch: `resources/prompts/runtime_memory_writer.txt`
   - Complexity: low. Type: prompt-only.

11. **Prompt-only: make router output robust (explicit schema, allowed values, default).**
   - Touch: `resources/prompts/runtime_router.txt`
   - Complexity: low. Type: prompt-only.

12. **Add a “tool_result surfaced” event/log (optional) to improve observability.**
   - Touch: `src/runtime/tool_loop.py` (emit `log_line` with result preview, size-limited).
   - Complexity: low. Type: mechanical code.

---

*Next: see `audit_file_inventory.md` for the complete per-file inventory (section 10).*
