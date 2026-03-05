# LLM Thalamus – Architecture & Codebase Audit (Overview)

## Index
- This file: `resources/Documentation/audit_overview.md` (sections 0–9, 11–12)
- File inventory: `resources/Documentation/audit_file_inventory.md` (section 10)
- Appendix: `resources/Documentation/audit_appendix.md` (supplementary tables/notes)

## 0) Document Control
- **Snapshot identifier:** provided snapshot (zip sha1 692b18d7223b5a1fe1a8d463f01aaa3d65126ee6)
- **Date:** 2026-03-05
- **How to use:** Start with sections 1–4 to understand execution/dataflow, then use section 6 (Node Catalog) and section 10 (Per-file Inventory) when planning changes. Section 12 provides an incremental roadmap referenced by F### IDs.
- **Conventions:**
  - Paths are **relative to repo root**.
  - Python modules are referenced by their import path (e.g., `runtime.tool_loop`).
  - **State** refers to the per-turn dict flowing through LangGraph (`runtime/state.py`).
  - **World** refers to durable JSON persisted as `world_state.json` (`controller/world_state.py`).
  - File references use inventory IDs: `F###` (see `audit_file_inventory.md`).

## 1) System Overview
### What the system does today
- Desktop (PySide6) chat application that runs a **LangGraph** turn pipeline over a local/remote LLM provider (currently Ollama is implemented in-tree).
- Maintains a **chat history JSONL** file and a **durable world state JSON** file, and uses an MCP client (OpenMemory) via **tools** when configured.
- Enforces a **central tool loop** (`runtime/tool_loop.py`) so nodes do not execute tools directly during LLM streaming; some nodes also do a **mechanical prefill** tool call pass (router) before the LLM call.

### Major subsystems
- **UI:** `src/ui/*` and `src/controller/worker.py` (Qt signals, streaming rendering, config dialog).
- **Runtime / orchestration:** `src/runtime/*` (deps, graph build, node runners, provider abstraction, tool loop, prompt loading/rendering, event emission).
- **Graph / nodes:** `src/runtime/graph_build.py` and `src/runtime/nodes/*` (router/context/memory/world/answer/reflection).
- **Tooling:** `src/runtime/tools/*` + `src/runtime/skills/*` + `src/controller/runtime_services.py` (skill gating, node policies, tool resources and deterministic handlers).
- **Persistence:** `src/controller/chat_history*.py`, `src/controller/world_state.py`, `var/llm-thalamus-dev/*` (dev sample data).
- **Resources:** `resources/prompts/*.txt`, `resources/config/config.json`, `resources/graphics/*`.

### High-level diagram
```text
UI (PySide6) ──> ControllerWorker.submit_message()
   │
   ├─ append user turn to chat_history.jsonl
   ├─ load/build Deps (LLM provider, prompt loader, config)
   ├─ build RuntimeServices (tools/resources, MCP client)
   └─ run_turn_runtime() (LangGraph compiled graph)
        router → (context_builder ↔ memory_retriever)? → world_modifier? → answer
              → reflect_topics → memory_writer → END
        │
        └─ Tool loop (streaming): provider.chat_stream() + deterministic tool execution
```

## 2) Repository Layout
### `src/`
- **Purpose:** Application code (UI + runtime).
- **Contains:** `config/`, `controller/`, `runtime/`, `ui/`, `tests/`, and `llm_thalamus.py` entrypoint.
- **Hotspots:** `runtime/tool_loop.py`, `runtime/nodes_common.py`, `runtime/graph_build.py`, `controller/worker.py`.

### `resources/`
- **Purpose:** Non-code assets shipped with app (prompts, config template, documentation, graphics).
- **Contains:** `prompts/` prompt templates, `config/config.json` template, `Documentation/` current audit docs, `graphics/` images.
- **Hotspots:** `resources/prompts/runtime_*.txt` (prompt contracts and placeholder tokens).

### `var/`
- **Purpose:** Development runtime data (example chat history + world state).
- **Contains:** `var/llm-thalamus-dev/data/chat_history.jsonl`, `var/llm-thalamus-dev/state/world_state.json`.
- **Hotspots:** None (sample data only).

Top-level files of note:
- `src/llm_thalamus.py`: UI entry point. F061
- `README.md`, `README_developer.md`, `CONTRIBUTING.md`, `Makefile`: packaging/docs/developer workflow.

## 3) Runtime Walkthrough (end-to-end)
### 3.1 Entry point and initialization
- **Entry point:** `src/llm_thalamus.py:main()` boots config via `config.bootstrap_config(argv)` and then launches the Qt UI.
```python
#!/usr/bin/env python3
from __future__ import annotations

import sys

from config import bootstrap_config


def main(argv: list[str]) -> int:
    cfg = bootstrap_config(argv)
```

### 3.2 Turn execution narrative (startup → completed user turn)
Observed in snapshot (no execution): the turn loop is driven by `controller/worker.py` calling `runtime.langgraph_runner.run_turn_runtime()`.

Numbered flow:
1. UI calls `ControllerWorker.submit_message(text)` (Qt slot) → spawns thread `_handle_message()`.
2. `_handle_message()` appends the user turn to JSONL history via `controller.chat_history.append_turn()`.
3. Build runtime dependencies: `runtime.deps.build_runtime_deps(cfg)` (LLM provider + prompt loader + role config).
4. Create per-turn `State` with `runtime.state.new_runtime_state(user_text=...)` and inject current `world` (copied from controller-owned world dict).
5. Build `RuntimeServices` once (worker init) via `controller.runtime_services.build_runtime_services()` (ToolResources + RuntimeToolkit; optional MCP client).
6. Call `run_turn_runtime(state, deps, services)` which runs the compiled LangGraph and yields structured events.
7. ControllerWorker consumes events and emits UI signals for streaming assistant output, thinking deltas, prompt capture, log lines, and world/state updates.
8. At end of turn, controller commits updated world state to disk (`controller.world_state.commit_world_state()`) and appends assistant turn to history JSONL.

### 3.3 Graph build and node sequence
- Compiled in `runtime/graph_build.py:build_compiled_graph(deps, services)` using `StateGraph(State)`.
```python
from runtime.nodes import llm_reflect_topics  # noqa: F401
from runtime.nodes import llm_memory_retriever  # noqa: F401
from runtime.nodes import llm_memory_writer  # noqa: F401


def build_compiled_graph(deps, services):
    g = StateGraph(State)

    # Nodes
    g.add_node("router", get("llm.router").make(deps, services))
```
Key edges / controller loop:
```python
        ctx = state.get("context") or {}
        if not isinstance(ctx, dict):
            return "answer"

        # Optional safety guard against infinite loops.
        rt = state.get("runtime") or {}
        hops = rt.get("context_hops") if isinstance(rt, dict) else None
        try:
            if isinstance(hops, int) and hops >= 5:
                # Too many controller hops; fall back to answer.
```

### 3.4 Tool loop behavior and tool result re-entry
- Central loop is `runtime.tool_loop.chat_stream()`; nodes call it via `runtime.nodes_common.run_structured_node()` / `run_streaming_answer_node()`.
- Tools are executed deterministically and results are appended as `Message(role='tool', ...)` back into the `messages` list for the next provider round.
- Important design choice (Option A): while tools are enabled, `response_format=None` to allow tool calls; after tools are done, a final pass may enforce `response_format` for JSON-only nodes.
```python
    if max_steps <= 0:
        raise RuntimeError(f"max_steps must be > 0 (got {max_steps})")

    # If no tools are enabled, this becomes a simple pass-through stream.
    if tools is None:
        req = ChatRequest(
            model=model,
            messages=messages,
            tools=None,
            response_format=response_format,
```
Tool execution + injection (deterministic handler, then append tool message):
```python
            final_req = ChatRequest(
                model=model,
                messages=messages,
                tools=None,
                response_format=response_format,
                params=_chat_params_from_mapping(params),
                stream=True,
            )
            _emit_llm_request(emitter=emitter, provider=provider, req=final_req, node_id=node_id, span_id=span_id, kind='final_format', step=step)
            for ev in provider.chat_stream(final_req):
```

### 3.5 Persistence updates
- Durable world state is loaded/created and committed atomically-ish by `controller/world_state.py`.
```python
    Minimal default. Expand later as needed.
    """
    w: World = {
        "updated_at": now_iso,
        "project": "",
        "topics": [],
        "goals": [],
        "rules": [],
        "identity": {
            "user_name": "",
```
- Chat history is JSONL under the path `cfg.message_file` via `controller/chat_history.py` and `controller/chat_history_service.py`.
- MCP OpenMemory is accessed **only** via `ToolResources.mcp` and tool handlers (see section 7).

### 3.6 Textual sequence diagram
```text
UI          ControllerWorker                LangGraph/Runtime                 LLM Provider        Tools/MCP
 | submit_message(text) -> _handle_message
 |    append_turn(human)
 |    deps=build_runtime_deps(cfg)
 |    state=new_runtime_state(text); state.world=world_copy
 |    for ev in run_turn_runtime(state,deps,services):
 |        emit UI stream/thinking/prompt/log/world/state updates
 |                              router(node) -> tool prefill (mechanical)
 |                              router(node) -> chat_stream(tools=None)
 |                              context_builder(node) -> chat_stream(tools=skill-gated)
 |                              memory_retriever(node) -> chat_stream(tools=skill-gated)
 |                              ... -> answer(streaming)
 |                              reflect_topics -> memory_writer
 |    commit world_state.json; append_turn(assistant)
```

## 4) State and Dataflow Model (core)
### 4.1 Canonical per-turn State shape
- Defined as `State = dict[str, Any]` in `src/runtime/state.py`; helper `new_runtime_state()` initializes the expected keys.
```python

class RuntimeState(TypedDict, total=False):
    task: RuntimeTask
    runtime: RuntimeRuntime
    context: RuntimeContext
    final: RuntimeFinal
    world: dict[str, Any]


State = dict[str, Any]
```

### 4.2 State structures and ownership
Per snapshot, these are the state namespaces used across nodes:
- `state['task']`: user input + routing decision. Created by `new_runtime_state()`, mutated by `llm.router` (writes `state['task']['route']`).
- `state['runtime']`: per-turn operational metadata (trace, status, issues, now/timezone, and an **emitter** installed by runner). Mutated by runners and controller instrumentation.
- `state['context']`: aggregator for retrieved evidence and directives. Mutated by context builder / retriever nodes; contains `sources` list (see `nodes_common.ensure_sources()`).
- `state['final']`: final user-facing output, typically `final.answer` set by `llm.answer`.
- `state['world']`: durable-ish data copied into the turn at start; later nodes may propose mutations and controller persists them.

### 4.3 Durable world state vs per-turn working state
- **Durable:** `world_state.json` (authoritative on disk; loaded into controller at boot; copied into each turn; committed after turn).
- **Working:** `State` (in-memory per turn; must remain JSON-serializable; passed node-to-node).

### 4.4 Pain points for strategic goals
- **Scoped state views:** nodes currently receive the full `State` dict; scoping would require projections at node boundaries or within `nodes_common.run_*` helpers.
- **Tool contract boundary:** tools are already centralized, but some nodes do mechanical prefill by directly invoking tool handlers (`run_tools_mechanically()` in `nodes_common.py`). This still respects "nodes never call MCP directly" (handlers route through ToolResources), but it is a second path to audit for policy consistency.
- **Deterministic `project_status`:** not present in snapshot (unknown). Implementing it likely touches `runtime/context_builder` prompts + a new tool/provider to load manifest data.

## 5) Subsystem Deep Dives (module-by-module)
### UI layer (`src/ui/*`)
- **Responsibilities:** Rendering chat, exposing config UI, showing streaming output and debug panes (thinking/prompt/log/world/state).
- **Key modules:** `ui/main_window.py`, `ui/chat_renderer.py`, `ui/config_dialog.py`, `ui/widgets.py`.
- **Depends on:** `controller.worker.ControllerWorker` Qt signals; config snapshot object.
- **Coupling hotspots:** UI assumes certain event types and payload shapes emitted by runtime emitter (see `runtime/emitter.py`, `runtime/events.py`).

### Runtime / orchestrator (`src/runtime/*`)
- **Responsibilities:** Provider abstraction (`providers/*`), prompt loading/rendering, node runner helpers, tool loop, LangGraph graph build & execution, event emission.
- **Key modules:** `runtime/deps.py`, `runtime/graph_build.py`, `runtime/langgraph_runner.py`, `runtime/nodes_common.py`, `runtime/tool_loop.py`, `runtime/prompt_loader.py`, `runtime/prompting.py`.
- **Public interfaces:** `build_runtime_deps(cfg)`, `build_compiled_graph(deps, services)`, `run_turn_runtime(state, deps, services)`.

### Graph / nodes (`src/runtime/nodes/*`)
- **Responsibilities:** Per-node prompt selection and state mutation contracts.
- **Pattern:** Each node file defines constants `NODE_ID`, `PROMPT_NAME`, and registers a `NodeSpec` via `runtime.registry.register()`.
- **Hotspots:** Router’s mechanical tool prefill; context-builder’s directive loop; world modifier applying ops.

### Tooling (`src/runtime/tools/*`, `src/runtime/skills/*`)
- **Responsibilities:** Define tools (schemas), implement deterministic handlers, gate tools by skill and node policy, provide resources (history/world/mcp).
- **Key modules:** `runtime/tools/toolkit.py`, `runtime/tools/resources.py`, `runtime/tools/bindings/*`, `runtime/skills/catalog/*`, `runtime/tools/policy/node_skill_policy.py`.

### Persistence (`src/controller/*` + `var/*`)
- **Responsibilities:** Chat history on disk; durable world state; optional MCP client setup.
- **Key modules:** `controller/chat_history.py`, `controller/chat_history_service.py`, `controller/world_state.py`, `controller/mcp/*`.

### Supporting utilities/scripts
- `src/tests/*`: probes and langgraph experiments; not wired into UI runtime.
- `Makefile`: dev shortcuts (exact targets: see file inventory).

## 6) Node Catalog
Nodes are registered via `runtime.registry.register(NodeSpec(...))` in each node module and wired into the graph in `runtime/graph_build.py`.

| Graph node key | NODE_ID | Prompt | Role key | Tool policy (node_key) | Graph position |
|---|---|---|---|---|---|
| `answer` | `llm.answer` | `resources/prompts/runtime_answer.txt` | `answer` | `answer` | see `runtime/graph_build.py` |
| `context_builder` | `llm.context_builder` | `resources/prompts/runtime_context_builder.txt` | `context_builder` | `context_builder` | see `runtime/graph_build.py` |
| `memory_retriever` | `llm.memory_retriever` | `resources/prompts/runtime_memory_retriever.txt` | `memory_retriever` | `memory_retriever` | see `runtime/graph_build.py` |
| `memory_writer` | `llm.memory_writer` | `resources/prompts/runtime_memory_writer.txt` | `memory_writer` | `memory_writer` | see `runtime/graph_build.py` |
| `reflect_topics` | `llm.reflect_topics` | `resources/prompts/runtime_reflect_topics.txt` | `reflect_topics` | `reflect_topics` | see `runtime/graph_build.py` |
| `router` | `llm.router` | `resources/prompts/runtime_router.txt` | `router` | `router` | see `runtime/graph_build.py` |
| `world_modifier` | `llm.world_modifier` | `resources/prompts/runtime_world_modifier.txt` | `world_modifier` | `world_modifier` | see `runtime/graph_build.py` |

Per-node details (state keys and tool access) are derived from reading node implementations; where a node’s exact output schema is defined only in prompt text, it is listed as **unknown from code** and should be confirmed by inspecting the prompt file.

## 7) Tooling System Catalog
### 7.1 Tool registry & discovery
- Skill-level grouping is hard-coded in `runtime/tools/toolkit.py:_load_skills()`.
- Enabled skills are in `runtime/skills/registry.py` and node allowlists are in `runtime/tools/policy/node_skill_policy.py`.
- Tool definitions/handlers are provided by `runtime/tools/providers/static_provider.py`, which loads from `runtime/tools/definitions/*` and `runtime/tools/bindings/*` (schema vs handler separation).

### 7.2 Tool loop (parsing/validation/execution)
- Implemented in `runtime/tool_loop.py` as a streaming loop over `provider.chat_stream()`.
- Tool calls are collected from `StreamEvent(type='tool_call')` and executed via `ToolSet.handlers[name](args_obj)`.
- Args parsing is strict JSON object (`_parse_tool_args_json()` + type check).
- Tool results are normalized to string (`_normalize_tool_result()`) and injected back as `Message(role='tool', ...)`.

### 7.3 Tool result formatting and injection back into model
- Injection is done by appending a tool message with `tool_call_id` so providers supporting tool call correlation can link the result.
- Additionally, the loop yields `StreamEvent(type='tool_result', text=...)` for UI/diagnostics.

### 7.4 Logging & observability
- LLM requests (including payload and optional curl) are emitted via `_emit_llm_request()` if provider exposes `build_chat_payload`/`build_chat_curl` and an emitter is installed.
- Tool calls/errors are logged via `emitter.factory.log_line(logger='tool_loop', ...)`.
- Missing/unknown from snapshot: log rotation/retention policy; any structured persistence of traces beyond UI display.

### 7.5 MCP usage boundaries
- MCP client exists at `controller/mcp/client.py` and is created only in `controller/runtime_services.py`.
- Tools use MCP via `ToolResources.mcp` (see `runtime/tools/resources.py` + `runtime/skills/catalog/mcp_memory_*.py`).
- Nodes do **not** import `controller.mcp.*` directly (boundary holds in snapshot).

## 8) Persistence Catalog
### 8.1 `world_state.json`
- **Location:** computed in `controller/worker.py:_compute_world_state_path()`; dev sample at `var/llm-thalamus-dev/state/world_state.json`.
- **Schema (code-defined default):** `controller/world_state.py:default_world()` includes keys: `updated_at`, `project`, `topics`, `goals`, `rules`, `identity` (+ optional `tz`).
- **Load/commit:** `load_world_state()` creates defaults if missing/corrupt and updates `updated_at` on load when `now_iso` passed; `commit_world_state()` writes temp then replace.

### 8.2 Chat history JSONL
- **Location:** `cfg.message_file` (see config schema); dev sample at `var/llm-thalamus-dev/data/chat_history.jsonl`.
- **API:** `controller/chat_history.py` provides append/read utilities; `controller/chat_history_service.py` wraps it for tool handlers.

### 8.3 MCP memory store (OpenMemory)
- **Presence:** optional; enabled when both `cfg.mcp_openmemory_url` and `cfg.mcp_openmemory_api_key` exist.
- **Usage:** via tool handlers (skill `mcp_memory_read` / `mcp_memory_write`).
- **Unknown from snapshot:** exact OpenMemory tool names/protocol semantics beyond what is implemented in `controller/mcp/*` and skill bindings.

### 8.4 Caches/logs
- `cfg.log_file` appears in config summary printing; runtime has an event bus/emitter and UI log window, but persistent log format/rotation is **unknown from snapshot** without running or inspecting config template details.

## 9) Dependency & Call Graph Summaries
### 9.1 Dependency overview (by package)
- `config/*` is imported by `llm_thalamus.py` only at boot; it locates project root and loads config template/user config.
- `controller/*` depends on `runtime/*` (build deps, run runtime) and Qt (signals/threads).
- `runtime/*` depends on LangGraph, provider implementation, and `runtime/tools/*` for tool wiring.
- `ui/*` depends on Qt and controller signals.

### 9.2 Key call chains (best-effort from imports + obvious call sites)
- `src/llm_thalamus.py:main()` → `config.bootstrap_config()` → `ControllerWorker(cfg)` → `ControllerWorker._handle_message()` → `runtime.deps.build_runtime_deps(cfg)` → `runtime.langgraph_runner.run_turn_runtime(state,deps,services)` → `runtime.graph_build.build_compiled_graph().compile()` → node callables from `runtime.nodes.*` → `runtime.nodes_common.run_*` → `runtime.tool_loop.chat_stream()` → `provider.chat_stream()`.

### 9.3 Change amplifiers (high fan-in/high coupling)
- `runtime/state.py` (state shape): imported broadly; adding/changing keys ripples across nodes and UI debug displays.
- `runtime/nodes_common.py` (runner utilities): shared execution semantics; modifications affect all nodes.
- `runtime/tool_loop.py` (tool semantics + formatting): affects all tool-capable calls; interacts with provider quirks.
- `controller/worker.py` (event plumbing): couples runtime emitter event schema to UI behavior.

## 11) Strategic Fit Check (forward plan alignment)
### 11.1 Obsidian as document store via MCP
- **Where it would plug in today:**
  - Add a new skill in `runtime/skills/catalog/` (e.g., `mcp_obsidian_read.py`) and wire it into `RuntimeToolkit._load_skills()`.
  - Implement tool definitions/handlers in `runtime/tools/definitions/` + `runtime/tools/bindings/` using `ToolResources.mcp`.
  - Update `runtime/tools/policy/node_skill_policy.py` to allow the skill for `context_builder` / `memory_retriever` only.
- **Likely refactors:** none strictly required; existing boundary (nodes → tools → MCP) already matches target.
- **Prompt-only possibilities:** context builder prompt can be tuned to request the new tool when needed, without code changes beyond adding the tool itself.

### 11.2 MCP isolated behind tool contracts; nodes never call MCP directly
- **Status in snapshot:** holds. MCP client is constructed in `controller/runtime_services.py` and passed through `ToolResources` to tool handlers; node code does not import MCP modules.
- **Risk:** mechanical prefill path (`run_tools_mechanically`) bypasses the LLM tool loop but still calls the same handlers; ensure policy/observability stays consistent (log emissions, max calls).

### 11.3 Deterministic `project_status` manifest compiled mechanically
- **Status in snapshot:** not present (unknown from snapshot).
- **Where it would plug in:**
  - As a new tool (e.g., `project_status_load`) with deterministic output, likely invoked by router/context_builder mechanically or via LLM tool call.
  - As an additional field under `state['context']` or `state['world']` with a fixed schema.
- **Refactor needs:** add a dedicated persistence module for the manifest + ensure node prompts reference it via placeholders.

### 11.4 Scoped state views / per-node projections
- **Status in snapshot:** not implemented; all nodes receive full `State` dict.
- **Where to implement:**
  - In `runtime.nodes_common.run_*` wrappers: build a per-node `tokens` dict and avoid passing the full state to token renderers.
  - Alternatively at LangGraph boundary: wrap node callables to provide a projected view and merge back allowed mutations.
- **Risk:** without a formal schema + enforcement, scoping can become ad-hoc and drift.

### 11.5 Prefer prompt tuning over code when feasible
- **Status in snapshot:** supported by design: prompt templates under `resources/prompts/` plus token rendering via `runtime/prompting.py` and node runner helpers.
- **Limitation:** some behavior is hard-coded in `graph_build.py` (node order and loop logic) and in tool gating policy; prompt tuning cannot change those without code changes.

## 12) Recommendations (incremental)
1. **Formalize State schema and add validators for node outputs**
   - Why: State keys and node output contracts are implicit; schema drift will hurt scoped views and deterministic manifests.
   - Touches: F155, F126, F120
   - Complexity/risk: med
   - Type: mechanical code
2. **Unify tool-call observability across both tool loop and mechanical prefill**
   - Why: Router uses `run_tools_mechanically()`; ensure consistent logging + error shaping like the tool loop.
   - Touches: F126, F124, F156
   - Complexity/risk: low
   - Type: mechanical code
3. **Add explicit node_key→skill policy docs and enforce deny-by-default**
   - Why: Tool boundary is a strategic pillar; make it harder to accidentally enable tools broadly.
   - Touches: F177, F182
   - Complexity/risk: low
   - Type: mechanical code
4. **Introduce a deterministic `project_status` loader tool (JSON) and wire it into context builder prompt**
   - Why: Enables the planned manifest compilation without pushing logic into nodes.
   - Touches: (new file), F154, F182, F018
   - Complexity/risk: med
   - Type: LLM-node code + mechanical code
5. **Split `world_state.json` into 'identity' vs 'project' sections with explicit ownership**
   - Why: Reduces coupling and supports scoped state views and safer world mutations.
   - Touches: F060, F125
   - Complexity/risk: med
   - Type: mechanical code + prompt
6. **Add a 'document store' skill scaffold for Obsidian/MCP (read-only first)**
   - Why: Aligns with strategy and can be introduced incrementally with clear tool contracts.
   - Touches: (new files under src/runtime/skills/catalog and src/runtime/tools/definitions/bindings), F058
   - Complexity/risk: med
   - Type: mechanical code
7. **Harden prompt token rendering with a strict 'unresolved token' error path**
   - Why: Prior logs referenced unresolved tokens; make failures deterministic and easy to diagnose.
   - Touches: F128, F127
   - Complexity/risk: low
   - Type: mechanical code
8. **Document the provider 'response_format' contract per provider and node role**
   - Why: Tool loop relies on toggling `response_format`; providers must implement this consistently.
   - Touches: F138, F140, F156
   - Complexity/risk: low
   - Type: docs + mechanical code

---
Sections 10 (Per-file Inventory) are in `audit_file_inventory.md`.