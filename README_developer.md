
# llm_thalamus — Developer README

This document describes the **internal architecture and contracts** of the runtime.

It is intended for developers modifying the system.

For usage instructions see **README.md**.

---

# Architectural Principles

1. **LLM nodes never perform side effects**
2. **All durable mutations occur through tools**
3. **MCP access must remain behind tool contracts**
4. **Prefer prompt changes over code changes**
5. **Runtime code should remain mechanical and deterministic**


---

# Runtime Overview

Entry point:

```
src/llm_thalamus.py
```

The entry point initializes:

- configuration
- runtime services
- the LangGraph pipeline
- the UI worker thread


Core runtime logic lives in:

```
src/runtime/
```


---

# Runtime Graph

Graph construction:

```
src/runtime/graph_build.py
```

Execution runner:

```
src/runtime/langgraph_runner.py
```

Node implementations:

```
src/runtime/nodes/
```


Current nodes:

| Node | File |
|-----|-----|
| context bootstrap | nodes/context_bootstrap.py |
| context builder | nodes/llm_context_builder.py |
| answer | nodes/llm_answer.py |
| reflect | nodes/llm_reflect.py |


Node prompts are loaded via:

```
src/runtime/prompt_loader.py
```


---

# Runtime State

Per‑turn state is defined in:

```
src/runtime/state.py
```

This state is **ephemeral** and passed between nodes.

Typical contents:

- user input
- context blocks
- model outputs
- tool calls
- intermediate reasoning artifacts


Durable state is stored separately.


---

# Durable World State

Location:

```
var/llm-thalamus-dev/state/world_state.json
```

Manager:

```
src/controller/world_state.py
```

Rules:

- LLM nodes must never write this file directly.
- Updates occur via the `world_apply_ops` tool.
- Updates must be deterministic operations.


---

# Tool System

The tool system is the **only mechanism for side effects**.

Components:

### Tool definitions

```
src/runtime/tools/definitions/
```

Describe:

- tool name
- input schema
- description visible to LLM


### Tool bindings

```
src/runtime/tools/bindings/
```

Contain the actual implementation logic.

Example bindings:

- memory_query
- memory_store
- world_apply_ops
- chat_history_tail


### Tool registry

```
src/runtime/tools/registry.py
```


### Tool loop

```
src/runtime/tool_loop.py
```

Responsibilities:

1. Parse tool calls emitted by the LLM
2. Validate arguments
3. Execute the binding
4. Inject results back into the model stream


---

# Provider Abstraction

Providers are implemented in:

```
src/runtime/providers/
```

Current provider:

```
ollama.py
```

Provider interface:

```
base.py
```

The abstraction allows different model backends to be swapped without modifying node logic.


---

# Skills System

Skills describe **what tools a node is allowed to use**.

Registry:

```
src/runtime/skills/registry.py
```

Skill catalog:

```
src/runtime/skills/catalog/
```

Examples:

- core_context
- core_world
- mcp_memory_read
- mcp_memory_write


Policies controlling which node can access which tools live in:

```
src/runtime/tools/policy/node_skill_policy.py
```


---

# Prompt System

Prompt templates are stored in:

```
resources/prompts/
```

Loaded via:

```
src/runtime/prompt_loader.py
```

Prompts contain placeholders that are filled by the runtime.


---

# UI Layer

Qt UI code lives in:

```
src/ui/
```

Key modules:

- `main_window.py`
- `chat_renderer.py`
- `widgets.py`
- `config_dialog.py`

The UI communicates with the runtime worker thread through the event bus.


---

# Event System

Runtime events are defined in:

```
src/runtime/events.py
```

Transport:

```
src/runtime/event_bus.py
```

Emitter helpers:

```
src/runtime/emitter.py
```

The event bus enables:

- UI updates
- prompt debugging
- tool activity tracing


---

# Testing

Experimental tests and probes live in:

```
src/tests/
```

These include:

- LangGraph behavior probes
- Ollama integration tests
- tool call format tests
- prompt parsing experiments


These are **development probes**, not yet a formal test suite.


---

# Planned Architectural Evolution

Future directions currently planned:

### Scoped State Views

Nodes should only receive the subset of runtime state they need.

### Deterministic Project Status

A compiled manifest representing project knowledge.

### MCP Document Store

External knowledge systems (Obsidian etc.) accessed through tools.

### Episodic Ledger

A SQLite log of conversation turns for deterministic replay.



---

# Contribution Guidelines

Before modifying code:

1. Prefer **prompt modifications** over code changes.
2. Maintain strict **tool contract boundaries**.
3. Keep runtime components **mechanical and deterministic**.
4. Avoid introducing hidden side effects.

Architecture changes should update:

```
resources/Documentation/
```

to keep the project documentation consistent.
