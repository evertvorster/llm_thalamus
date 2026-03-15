# Planner / Executor Architecture (Future Design)

Status: **Design document — not yet implemented**

This document describes the planned architecture for introducing a **planner/executor feedback loop** in `llm_thalamus`. This design supports multi-step tasks, tool orchestration, and richer operational reasoning while keeping prompts and node responsibilities small and deterministic.

This design builds on the existing node architecture:

* context_builder
* reflect
* answer
* (future) planner
* (future) executor

---

# Motivation

Current architecture already separates several responsibilities:

| Node            | Responsibility                           |
| --------------- | ---------------------------------------- |
| context_builder | reconstruct working context for the turn |
| reflect         | curate memory/topics for the next turn   |
| answer          | produce user-facing output               |

However, complex tasks that require:

* multiple tool calls
* intermediate reasoning
* plan generation
* artifact creation
* world state changes

do not map cleanly to a single node.

A planner/executor loop allows the system to:

* execute multi-step plans
* adapt to execution results
* recover from failures
* keep the final answer node simple.

---

# High Level Architecture

```
User
  ↓
context_builder
  ↓
reflect (topic extraction)
  ↓
planner
  ↓
executor
  ↓
planner
  ↓
executor
  ...
  ↓
planner (decides task complete)
  ↓
answer
  ↓
reflect (store significant information)
```

Planner and executor form a **feedback loop** until the planner decides the job is complete.

---

# Node Responsibilities

## Context Builder

Purpose: reconstruct a usable context window.

Responsibilities:

* gather relevant chat history
* gather memory retrieval results
* gather world state fragments
* assemble compact context
* feed downstream nodes

This replaces the "huge chat history prompt" typical in LLM systems.

---

## Reflect Node

Purpose: curate long-term continuity.

Responsibilities:

* extract discussion topics
* identify memory candidates
* store significant information
* maintain topic/world summaries

Reflect does **not** orchestrate operational actions.

---

## Planner Node (Future)

Purpose: determine *what should happen*.

Responsibilities:

* interpret user operational intent
* create or update plans
* select the next step
* decide whether execution is needed
* determine completion conditions
* summarize results for the answer node

Planner **owns task completion decisions**.

Planner may:

* read plans
* create plans
* revise plans
* delegate steps to executor

Planner should use tools sparingly.

---

## Executor Node (Future)

Purpose: perform concrete actions.

Responsibilities:

* execute one step requested by the planner
* use tools
* update artifacts
* mutate world state if required
* report execution results

Executor **does not decide task completion**.

Executor returns structured results to the planner.

---

## Answer Node

Purpose: communicate with the user.

Responsibilities:

* read planner summary
* read context
* produce final user response
* avoid operational reasoning or tool orchestration

---

# Planner / Executor Feedback Loop

Planner and executor exchange structured messages.

Planner decides:

* next step
* whether execution should continue
* whether the task is complete
* whether user clarification is required

Executor reports:

* success
* failure
* blocked conditions
* artifacts created
* observations

---

# Task Session Model

Planner and executor communicate through a **task session object**.

This is richer than the existing turn state object.

Example structure:

```json
{
  "task_id": "turn-123-plan-1",
  "goal": "Create and store an Obsidian integration plan",
  "status": "in_progress",
  "plan": {
    "steps": [
      {"id": "s1", "title": "Inspect project state", "status": "complete"},
      {"id": "s2", "title": "Draft integration outline", "status": "complete"},
      {"id": "s3", "title": "Write note to Obsidian", "status": "in_progress"}
    ]
  },
  "thread": [
    {
      "kind": "planner_step_selected",
      "step_id": "s3",
      "content": "Write integration outline to Obsidian note."
    },
    {
      "kind": "executor_result",
      "step_id": "s3",
      "status": "blocked",
      "content": "Target folder missing."
    },
    {
      "kind": "planner_replan",
      "content": "Create folder first."
    }
  ]
}
```

---

# Summary

The planner/executor architecture enables:

* multi-step tasks
* adaptive planning
* cleaner tool orchestration
* smaller prompts
* clearer node responsibilities
