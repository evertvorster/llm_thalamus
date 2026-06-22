
# llm_thalamus

**llm_thalamus** is a rich **Qt desktop GUI for the [pi coding agent](https://pi.dev/)**.

It wraps `pi --mode rpc` in a native Qt window, providing:

- **Rich message rendering** — LaTeX, code blocks with syntax highlighting, thinking blocks
- **Session management** — browse, resume, and fork pi sessions
- **Brain activity visualization** — animated brain widget during thinking
- **`/`-command palette** — discover and invoke pi commands, extensions, skills, and templates
- **Native desktop feel** — no Electron, no Tauri, just PySide6 Qt

## Status

**Under active redevelopment.** The original LangGraph backend is being replaced with a `pi --mode rpc` bridge. See `pi-rpc-integration.md` for the mission and `rpc-signal-mapping.md` for the detailed implementation plan.

## What stays

- `src/ui/chat_renderer.py` — rich message rendering
- `src/ui/widgets.py` — ChatInput, BrainWidget
- Graphics (brain images)

## What's new

- `src/controller/pi_bridge.py` — PiRPCBridge (spawns pi, reads RPC events, emits Qt signals)
- `resources/pi-config/` — pi config directory (models, subagents, settings)

## What's gone

- `src/runtime/` — LangGraph backend
- `src/controller/mcp/` — MCP client
- `src/controller/world_state.py`, `runtime_services.py`, `worker.py`
- `src/config/` — replaced by pi config dir
- `resources/config/` — same
- `src/ui/config_dialog.py` — config is filesystem-based now
- `src/tests/` — LangGraph integration tests

## Direction

See [`pi-rpc-integration.md`](./pi-rpc-integration.md) for the full mission document.
See [`rpc-signal-mapping.md`](./rpc-signal-mapping.md) for the RPC-to-Qt signal mapping and implementation plan.
- **LLM nodes never directly access persistence layers or MCP services.**


---

# Current Architecture

The runtime executes a small deterministic node pipeline.

Current graph:

```
context_bootstrap
      ↓
llm.primary_agent  ⇄ tool_loop
      ↓
llm.reflect_topics
      ↓
llm.reflect_memory
```

### Node responsibilities

| Node | Purpose |
|-----|-----|
| `context_bootstrap` | Mechanically prefills recent chat and memory evidence for the turn |
| `llm.primary_agent` | Plans, retrieves when needed, and emits the user-facing answer |
| `llm.reflect_topics` | Performs post-answer topic continuity and canonical topic maintenance |
| `llm.reflect_memory` | Performs post-answer durable-memory extraction and storage |


All durable changes (memory writes, world updates, etc.) occur through **tools**, never directly inside nodes.


---

# Repository Layout

```
src/
  config/        Configuration loading and validation
  controller/    Runtime services and persistence managers
  runtime/       Graph construction, nodes, tools, providers
  ui/            Qt user interface
  tests/         Runtime probes and experiments

resources/
  prompts/       Prompt templates for LLM nodes
  config/        Runtime configuration files (config, LLM backends, MCP servers, internal tools)
  graphics/      UI assets

var/
  llm-thalamus-dev/
    state/       Durable world state (world_state.json)
    data/        Chat history (chat_history.jsonl)
```


---

# Key Concepts

## World State

Persistent JSON state representing durable knowledge about the system.

Location:

```
var/llm-thalamus-dev/state/world_state.json
```

World updates are applied through the **`world_apply_ops` tool**.

The LLM never writes this file directly.

---

## Tool System

All external actions occur through **tools**.

Example tools:

- `chat_history_tail`
<<<<<<< Updated upstream
- `openmemory_query`
- `openmemory_store`
=======
- `read`
- `write`
- `edit`
- `bash`
- `mempalace_search`
- `mempalace_add_drawer`
>>>>>>> Stashed changes
- `world_apply_ops`

Tools are defined in:

```
src/runtime/tools/definitions/
```

Bindings that perform the actual work live in:

```
src/runtime/tools/bindings/
```

Execution is controlled by:

```
src/runtime/tool_loop.py
```

---

## Prompts

Prompt templates live in:

```
resources/prompts/
```

Current runtime prompts:

```
runtime_primary_agent.txt
runtime_reflect_topics.txt
runtime_reflect_memory.txt
```

Prompt placeholders are replaced mechanically by the runtime.

---

# Running

Typical development run:

```
make run
```

Direct execution:

```
python -m src.llm_thalamus
```


---

# Requirements

- Python 3.11+
- A local LLM server (llama-cpp server at `http://127.0.0.1:8080/v1` by default, or Ollama, or LM Studio)
- Qt (PySide6 recommended)

Example (Arch Linux):

```bash
sudo pacman -S python python-pyside6
```

The default configuration uses the llama-cpp HTTP server. Install and start it separately:

```bash
# Start llama.cpp server on port 8080 with your model
./server -m /path/to/model.gguf -c 4096
```

Other backends (Ollama, LM Studio) are available in `resources/config/llm_backends.json`.

---


# Configuration

Runtime configuration lives in `resources/config/`:

| File | Purpose |
|------|---------|
| `config.json` | Runtime settings (model roles, sampling params, policies, UI settings) |
| `llm_backends.json` | Available LLM backends (llama-cpp, Ollama, LM Studio) |
| `mcp_servers.json` | MCP server definitions (currently MemPalace) |
| `internal_tools.json` | Internal tool approval policies (auto vs. ask) |

---

# MCP Integration

llm_thalamus connects to external MCP servers through a built-in client.

Current MCP servers:

| Server | Transport | Purpose |
|--------|-----------|--------|
| `mempalace` | stdio (`python -m mempalace.mcp_server`) | Durable memory persistence |

MCP tools are exposed to LLM nodes through **skills** (see the Tool System section above).
The MemPalace MCP server provides `mempalace_search`, `mempalace_add_drawer`, and other memory operations.


---

# Project Status

The project is an **active experimental runtime** focused on building a deterministic architecture for LLM agents.

Near‑term goals:

- Scoped state views for nodes
- Deterministic `project_status` manifests
- MCP integration behind tool contracts
- Obsidian document store integration
- Improved prompt inspection and UI tooling


---

# License

See `LICENSE.md`.
