# ADD_NODE_CHECKLIST.md

## Purpose

This document defines the repeatable procedure for adding a new node to `llm_thalamus v2` without breaking:

* streaming
* planner/executor integration
* world state invariants
* UI refresh logic
* prompt rendering

This checklist exists because adding `world_update_node` exposed several non-obvious integration steps.

---

# Phase 0 — Define Scope

Before writing any code:

* [ ] Define node name.
* [ ] Define **single responsibility** (must do one job only).
* [ ] Classify node:

  * Mechanical
  * LLM-only
  * Hybrid (LLM produces structured output; mechanical applies it)
* [ ] Decide which state areas it reads/writes:

  * `task`
  * `context`
  * `world`
  * `runtime`

If the node mutates persistent world state, confirm:

* [ ] It will reuse `commit_world_state()` from `world_state.py`
* [ ] It will update `state["world"]` in-memory immediately after commit

---

# Phase 1 — Prompt (If LLM-Based)

If the node uses a prompt:

* [ ] Create `resources/prompts/<node>.txt`
* [ ] If `PromptLoader.render()` uses `str.format()`, then:

  **CRITICAL RULE:**

  * Escape all literal JSON braces:

    * `{` → `{{`
    * `}` → `}}`
  * Do NOT escape real placeholders like `{user_input}`

This prevents runtime crashes like:

```
KeyError: '"termination"'
KeyError: '"world_delta"'
```

* [ ] Enforce strict JSON output if the node parses JSON.
* [ ] Explicitly forbid markdown, prose, code fences.

---

# Phase 2 — Node Implementation

Create:

```
src/orchestrator/nodes/<node>_node.py
```

Node must expose:

```python
run_<node>_node(state, deps, emit=None) -> State
```

Checklist:

* [ ] If using LLM streaming:

  * Forward every chunk:

    ```python
    emit({"type": "log", "text": chunk})
    ```
* [ ] Parse JSON defensively.
* [ ] On parse error:

  * Append `runtime.reports` entry
  * Do NOT crash
* [ ] Append breadcrumb:

  ```python
  state["runtime"]["node_trace"].append("<node>:committed")
  ```
* [ ] Append human-readable report:

  ```python
  state["runtime"]["reports"].append(...)
  ```

---

# Phase 3 — Integration Pattern

There are TWO supported integration styles in this codebase.

---

## Pattern A — Planner/Executor Action (Recommended)

Used for:

* `world_update`
* `memory_retrieval`
* `episode_query`
* `chat_messages`
* `world_fetch_full`

Checklist:

* [ ] Add action to `_ALLOWED_ACTIONS` in `planner_node.py`
* [ ] Add dispatch branch in `executor_node.py`
* [ ] Ensure `emit` is forwarded into node call
* [ ] Ensure model key exists in `deps.models`

This does NOT require changes to:

* `graph_build.py`
* `graph_policy.py`

---

## Pattern B — Full LangGraph Node

Used only if:

* Node is part of routing graph directly
* It must appear as node_start/node_end in graph

Checklist:

* [ ] Add wrapper factory in `graph_nodes.py`
* [ ] Register in `graph_build.py`
* [ ] Update routing in `graph_policy.py`

---

# Phase 4 — World State Mutation Rules

If node mutates world:

* [ ] Reuse `commit_world_state()` (never duplicate mutation logic)
* [ ] Update `state["world"]` after commit
* [ ] Add `runtime.node_trace` breadcrumb
* [ ] Decide whether worker should refresh `_world` pre-reflect

Note:

Worker currently refreshes world before reflect if it sees:

```
"world_update:committed"
```

See `ControllerWorker._handle_message()` for reference. 

---

# Phase 5 — UI Streaming Contract

The UI only sees:

```
Event(type="log")
Event(type="final")
```

Checklist:

* [ ] Ensure your node emits `log` events.
* [ ] Confirm logs appear in thinking panel.
* [ ] Ensure no silent failures.

---

# Phase 6 — Termination Discipline

Planner rules:

* `finalize` is NOT termination.
* After finalize runs once, planner must emit:

  ```json
  {"termination": {...}}
  ```
* Planner must not loop on finalize.

If adding new planner actions:

* [ ] Update planner prompt to document the new action.
* [ ] Clearly define when to use it.
* [ ] Clarify difference between action vs termination.

---

# Phase 7 — Smoke Test Checklist

After adding node:

* [ ] Planner selects new action.
* [ ] Executor dispatch runs node.
* [ ] Node logs appear in thinking panel.
* [ ] Node writes expected state changes.
* [ ] No `.format()` KeyError crashes.
* [ ] No reflect JSON parse regressions.
* [ ] UI world panel refreshes as expected.

---

# Known Failure Modes (Write These On The Wall)

### 1. Prompt Brace Failure

Literal JSON in prompts MUST be escaped.
Failure signature:

```
KeyError: '"something"'
```

### 2. Emit Not Forwarded

If logs don’t appear:

* Check executor dispatch passes `emit`
* Check node uses `emit({"type":"log"...})`

### 3. World State Double Mutation

If two nodes modify world in same turn:

* Ensure worker `_world` is refreshed before reflect
* Ensure reflect no longer mutates fields owned by new node

---

# Philosophy Reminder

* Planner decides.
* Executor performs mechanical steps.
* Nodes do one job.
* World mutation logic lives in `world_state.py`.
* Reflect is historian + inference only (not structural editor).
* No silent data mutation.
