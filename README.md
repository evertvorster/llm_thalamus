# llm_thalamus

llm_thalamus is a local-first, graph-orchestrated LLM runtime designed around
explicit state management, deterministic world updates, and tool-mediated side effects.

It combines:

- A LangGraph-style node execution pipeline
- Structured durable world state (JSON)
- SQLite-backed episodic and memory stores
- A provider-agnostic LLM abstraction (Ollama supported)
- A Qt desktop UI
- Strict tool-contract boundaries for all side effects

The architectural philosophy is:

- Nodes reason. Tools mutate.
- Prefer prompt tuning over branching logic.
- Keep world state deterministic and inspectable.
- Keep MCP isolated behind tool contracts.

---

# Architecture Overview

Minimal runtime graph:

User Input
    ↓
llm.router
    ↓
llm.context_builder
    ↓
llm.memory_retriever
    ↓
llm.answer  ⇄  Tool Loop
    ↓
llm.reflect_topics
    ↓
llm.memory_writer
    ↓
llm.world_modifier

LLM nodes do not perform direct side effects.
All durable mutations pass through tools.

---

# Repository Layout

src/
  config/        Configuration loading and validation
  controller/    Runtime services, MCP client, world state service
  runtime/       Graph construction, nodes, tool loop, providers
  ui/            Qt UI
  tests/         Runtime probes and integration experiments

resources/
  prompts/       Per-node prompt templates
  config/        Runtime configuration

var/
  llm-thalamus-dev/
    data/        SQLite stores (memory + episodes)
    state/       world_state.json

---

# Requirements

- Python 3.11+
- Ollama (for local model execution)
- Qt (PySide6 or PyQt6 depending on environment)

Example (Arch Linux):

sudo pacman -S python ollama

---

# Configuration

Primary runtime config:

resources/config/config.json

World state location:

var/llm-thalamus-dev/state/world_state.json

Persistent stores:

var/llm-thalamus-dev/data/memory.sqlite
var/llm-thalamus-dev/data/episodes.sqlite

---

# Running

Development run:

make run

Direct run:

python -m src.llm_thalamus

---

# Tooling Model

Tool definitions:
src/runtime/tools/definitions/

Tool bindings:
src/runtime/tools/bindings/

Tool policy enforcement:
src/runtime/tools/policy/node_skill_policy.py

Tool loop implementation:
src/runtime/tool_loop.py

Nodes may emit structured tool calls.
Tool results are injected back into model context.

---

# Persistence Model

Durable:

- world_state.json
- memory.sqlite
- episodes.sqlite

Ephemeral:

- Per-turn runtime state
- Prompt-rendered context

World mutations occur through:
- world_apply_ops tool
- llm_world_modifier node

---

# Strategic Direction

Planned evolution includes:

- Scoped per-node state projections
- Deterministic project_status manifest
- Obsidian-backed document store via MCP tools
- Stronger mechanical/LLM separation

---

# License

See LICENSE.md
