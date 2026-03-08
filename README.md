
# llm_thalamus

**llm_thalamus** is a local‑first experimental LLM runtime focused on **deterministic orchestration of local models**.

The system combines:

- A **LangGraph‑style node execution pipeline**
- A **strict tool contract boundary** for all side effects
- **Durable world state** stored as JSON
- **Prompt‑driven reasoning nodes**
- **Provider‑agnostic model execution** (currently Ollama)
- A **desktop Qt UI** for interactive use and debugging

The core design philosophy is:

- **Nodes reason. Tools mutate.**
- **Prompts define behavior whenever possible.**
- **Runtime code should remain mechanical and deterministic.**
- **All side effects pass through tools.**
- **LLM nodes never directly access persistence layers or MCP services.**


---

# Current Architecture

The runtime executes a small deterministic node pipeline.

Current graph:

```
context_bootstrap
      ↓
llm_context_builder
      ↓
llm_answer  ⇄ tool_loop
      ↓
llm_reflect
```

### Node responsibilities

| Node | Purpose |
|-----|-----|
| `context_bootstrap` | Initializes per‑turn runtime state |
| `llm_context_builder` | Assembles context blocks and retrieves information |
| `llm_answer` | Generates the assistant reply and may invoke tools |
| `llm_reflect` | Extracts structured topics/world updates |


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
  config/        Runtime configuration file
  graphics/      UI assets

var/
  llm-thalamus-dev/
    state/       Durable world state
    data/        Chat history
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
- `memory_query`
- `memory_store`
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
runtime_context_builder.txt
runtime_answer.txt
runtime_reflect.txt
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
- Ollama (for local model execution)
- Qt (PySide6 recommended)


Example (Arch Linux):

```
sudo pacman -S python ollama python-pyside6
```


---

# Configuration

Primary runtime config:

```
resources/config/config.json
```

This file defines:

- model roles
- sampling parameters
- provider configuration
- runtime policies


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
