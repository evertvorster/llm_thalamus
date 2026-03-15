# Tool Activity UI Event Flow

## Purpose

This document records the architecture and invariants for exposing node activity and tool activity in the chat timeline UI.

The goal is to make non-answer node execution visible to the user without treating controller activity as chat messages.

This work enables:

- visible controller-node execution
- visible tool calls and tool results
- future approval / denial / auto-approval hooks
- cleaner debugging of runtime behavior

---

## Design Summary

The system now uses the **existing runtime event spine** as the single source of truth for UI-visible activity.

### Core rule

**Do not build a separate UI-only event path.**

Activity must flow through the same runtime event system already used for runtime visibility and debugging.

---

## User-Facing Model

The chat timeline now contains two categories of items:

### 1. Chat turns

These are normal conversational bubbles.

Sources:

- user message
- answer node assistant output

### 2. Activity rows

These are lightweight timeline entries for controller activity.

Sources:

- non-answer node lifecycle events
- tool execution events

### Important rule

**Only the answer node may emit assistant-visible prose.**

Controller nodes must never appear as assistant chat messages.

---

## Runtime Event Spine

The event flow is:

```text
TurnEventFactory
  -> TurnEmitter
  -> EventBus
  -> run_turn_runtime()
  -> ControllerWorker
  -> MainWindow
  -> ChatRenderer