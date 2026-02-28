# llm_thalamus — Developer README

This document is intended for contributors and maintainers.
It describes internal contracts, state models, node expectations,
and architectural boundaries.

If you are looking for general usage instructions, see README.md.

---

# Core Architectural Rules

1. LLM nodes do not perform side effects.
2. All durable mutations must occur through tools.
3. MCP must only be accessed behind tool contracts.
4. Prefer prompt tuning over runtime branching logic.
5. Maintain strict separation between:
   - Mechanical execution
   - LLM reasoning

---

# Runtime Graph (Minimal Graph)

Current node order:

llm.router
llm.context_builder
llm.memory_retriever
llm.answer
llm.reflect_topics
llm.memory_writer
llm.world_modifier

Graph construction lives in:
src/runtime/graph_build.py

Node registration:
src/runtime/graph_nodes.py

Execution runner:
src/runtime/langgraph_runner.py

---

# State Model

## Durable State

Location:
var/llm-thalamus-dev/state/world_state.json

Loaded and managed by:
src/controller/world_state.py

Characteristics:
- Deterministic JSON
- Append/update through structured operations
- Never mutated directly by LLM nodes

Mutation pathway:
llm_world_modifier → world_apply_ops tool

---

## Memory Stores

Location:
var/llm-thalamus-dev/data/

- memory.sqlite
- episodes.sqlite

Accessed via:
src/runtime/tools/bindings/memory_query.py
src/runtime/tools/bindings/memory_store.py

Nodes must not directly access SQLite.

---

## Per-Turn Runtime State

Defined in:
src/runtime/state.py

Contains:
- User input
- Context blocks
- Tool call records
- Model outputs
- Intermediate reasoning

This state is ephemeral.

---

# Tool System

Tool definitions:
src/runtime/tools/definitions/

Bindings:
src/runtime/tools/bindings/

Policy enforcement:
src/runtime/tools/policy/node_skill_policy.py

Tool loop:
src/runtime/tool_loop.py

Rules:

- Nodes emit structured tool calls.
- Tool loop validates call.
- Binding executes mechanical logic.
- Tool result is injected back into model context.
- Loop continues until model stops calling tools.

---

# Prompt System

Prompt files:
resources/prompts/

Per-node prompts:

- runtime_router.txt
- runtime_context_builder.txt
- runtime_memory_retriever.txt
- runtime_answer.txt
- runtime_reflect_topics.txt
- runtime_memory_writer.txt
- runtime_world_modifier.txt

Prompt loader:
src/runtime/prompt_loader.py

Prompt rendering:
src/runtime/prompting.py

Guidelines:

- Avoid embedding business logic in code when prompt refinement is sufficient.
- Keep placeholder usage consistent.
- Document any new placeholders introduced.

---

# Provider Abstraction

Provider base:
src/runtime/providers/base.py

Ollama provider:
src/runtime/providers/ollama.py

Factory:
src/runtime/providers/factory.py

Configuration-driven role mapping:
resources/config/config.json

Roles typically include:

- router
- answer
- reflect
- memory
- world

---

# MCP Boundary

MCP client:
src/controller/mcp/client.py

MCP must never be imported directly by LLM nodes.

If MCP access is needed:
1. Define a tool
2. Implement binding
3. Add policy entry
4. Update prompt to use tool

---

# Node Contracts

Each node must define:

- Expected input state keys
- Output state keys
- Tool permissions
- Associated prompt file

Nodes should remain pure functions over state + tool loop.

---

# Adding a New Node

1. Create node file under:
   src/runtime/nodes/

2. Add prompt under:
   resources/prompts/

3. Register node in:
   graph_nodes.py

4. Add to graph in:
   graph_build.py

5. Update tool policy if needed.

---

# Testing & Probes

Probe tests:
src/tests/

These are integration-style tests, not strict unit tests.

---

# Future Strategic Goals

- Scoped state projections per node
- Deterministic project_status compiler
- Obsidian-backed document store via MCP tools
- Stronger separation between world state and knowledge store

---

# Contribution Guidance

Before writing code:

- Ask: can this be solved by prompt adjustment?
- Ensure no side effects occur in nodes.
- Preserve mechanical determinism.
- Avoid widening state visibility unnecessarily.

---

End of Developer README.
