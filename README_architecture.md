# LLM Thalamus --- Architecture Overview

This document provides a concise architectural overview of the
**llm_thalamus** system. It sits between the high‑level `README.md` and
the detailed audit documents in `resources/Documentation/`.

Purpose of this document:

-   Provide a **quick mental model** of how the system works
-   Explain **major subsystems and their responsibilities**
-   Show the **runtime execution flow**
-   Identify **extension points** for future development

For full technical detail see:

-   `resources/Documentation/audit_overview.md`
-   `resources/Documentation/audit_file_inventory.md`
-   `resources/Documentation/audit_appendix.md`

------------------------------------------------------------------------

# 1. System Concept

**llm_thalamus** is a local orchestration runtime for large language
models designed to behave like a structured cognitive system rather than
a single prompt/response loop.

The project implements:

-   A **deterministic runtime pipeline**
-   A **LangGraph execution graph**
-   A **tool‑mediated environment interaction layer**
-   A **durable world state**
-   A **prompt‑driven reasoning architecture**

The design goal is to make LLM behaviour:

-   observable
-   deterministic where possible
-   debuggable
-   extensible

------------------------------------------------------------------------

# 2. High‑Level Architecture

    User Input
        │
        ▼
    UI Layer (Qt)
        │
        ▼
    Controller / Worker
        │
        ▼
    Runtime Graph Runner
        │
        ▼
    LangGraph Node Pipeline
        │
        ├─ context_bootstrap
        ├─ llm.primary_agent
        └─ llm.reflect
        │
        ▼
    Tool Loop (optional during node execution)
        │
        ▼
    World State + Memory Updates
        │
        ▼
    UI Rendering + Event Stream

------------------------------------------------------------------------

# 3. Major Subsystems

## 3.1 UI Layer

Directory:

    src/ui/

Responsibilities:

-   Main application window
-   Chat display and rendering
-   Configuration dialogs
-   Event‑driven updates from the runtime

The UI listens to events emitted from the runtime event bus and renders
them in real time.

Key files:

-   `main_window.py`
-   `chat_renderer.py`
-   `config_dialog.py`
-   `widgets.py`

------------------------------------------------------------------------

## 3.2 Controller Layer

Directory:

    src/controller/

Responsibilities:

-   Chat history management
-   Worker orchestration
-   World state loading and persistence
-   Runtime service wiring
-   MCP client integration

Key components:

    worker.py
    runtime_services.py
    world_state.py
    chat_history_service.py

The worker is responsible for coordinating each user turn.

------------------------------------------------------------------------

## 3.3 Runtime Layer

Directory:

    src/runtime/

Responsibilities:

-   Graph construction
-   Node execution
-   Tool handling
-   Prompt construction
-   Provider abstraction

Key modules:

    graph_build.py
    langgraph_runner.py
    tool_loop.py
    nodes_common.py
    prompting.py
    state.py

------------------------------------------------------------------------

## 3.4 Node System

Directory:

    src/runtime/nodes/

Nodes represent the reasoning stages in the pipeline.

Current nodes:

  Node                  Purpose
  --------------------- ---------------------------------------
  context_bootstrap     Mechanically prefills evidence for the turn
  llm.primary_agent     Plans, retrieves, and emits the final user answer
  llm.reflect           Performs post-answer topic and memory maintenance

Nodes communicate exclusively through the shared **state object**.

------------------------------------------------------------------------

## 3.5 Tooling System

Directory:

    src/runtime/tools/

Responsibilities:

-   Tool definitions
-   Tool execution
-   Tool registry
-   Node tool policies

The tooling layer ensures the LLM interacts with the environment **only
through controlled contracts**.

Structure:

    definitions/
    bindings/
    policy/
    providers/
    registry.py
    toolkit.py

------------------------------------------------------------------------

## 3.6 Skills System

Directory:

    src/runtime/skills/

Skills define reusable capabilities exposed to nodes.

Examples:

    core_context
    core_world
    mcp_memory_read
    mcp_memory_write

Skills determine what tools a node is allowed to use.

------------------------------------------------------------------------

# 4. Prompt System

Prompts live in:

    resources/prompts/

Current prompts:

    runtime_primary_agent.txt
    runtime_reflect.txt

Prompt templates are loaded through `Deps.load_prompt()` and rendered
through `prompting.py` using runtime state data.

------------------------------------------------------------------------

# 5. Persistence

Runtime state is split into two layers.

## Durable World State

Location:

    var/llm-thalamus-dev/state/world_state.json

Stores:

-   long‑term context
-   system identity
-   accumulated state changes

## Chat History

Location:

    var/llm-thalamus-dev/data/chat_history.jsonl

Stores raw conversation turns.

------------------------------------------------------------------------

# 6. LLM Provider Layer

Directory:

    src/runtime/providers/

Purpose:

Provide a unified interface to different model backends.

Current provider:

    ollama.py

Provider selection occurs through configuration in:

    resources/config/config.json

------------------------------------------------------------------------

# 7. Event System

The runtime emits structured events through:

    event_bus.py
    events.py
    emitter.py

These events power:

-   UI updates
-   debugging tools
-   logging streams

------------------------------------------------------------------------

# 8. Execution Flow (User Turn)

1.  User sends message via UI
2.  Worker receives the request
3.  Runtime services initialize the environment
4.  LangGraph runner executes the node pipeline
5.  Each node constructs prompts and calls the LLM
6.  Tool calls (if present) are executed via `tool_loop.py`
7.  Results are fed back to the model
8.  Final answer emitted
9.  Reflection node updates world state
10. Events streamed to UI

------------------------------------------------------------------------

# 9. Extension Points

Key areas for extending the system:

### New Nodes

Add under:

    runtime/nodes/

and register in:

    graph_build.py

### New Tools

Add:

    runtime/tools/definitions/
    runtime/tools/bindings/

### New Skills

Add under:

    runtime/skills/catalog/

### New LLM Providers

Implement:

    runtime/providers/base.py

------------------------------------------------------------------------

# 10. Future Architecture Direction

Planned evolution includes:

-   MCP‑based document stores (Obsidian)
-   deterministic `project_status` manifests
-   scoped state views per node
-   expanded skill libraries
-   deeper tool auditing
-   improved prompt inspection tooling

------------------------------------------------------------------------

# 11. Philosophy

The system intentionally prefers:

-   **prompt engineering over code complexity**
-   **observable reasoning pipelines**
-   **tool contracts instead of direct integrations**
-   **deterministic runtime structure**

The goal is to treat the LLM as a **component inside a larger cognitive
system**, not the system itself.
