# Runtime Architecture Status (March 2026)

This document describes the state of the codebase after the MCP integration, tool approval system, and UI improvements.

It functions as an **explicit architecture changelog**.

---

# Major Changes

## MCP System Introduced

The system now supports multiple MCP servers.

Key features:

* startup discovery of MCP tools
* per-tool approval policies
* runtime tool schema snapshot
* UI configuration for servers
* inline approval system

---

# MCP Configuration

New config file:

```
mcp_servers.json
```

Contains:

* server definitions
* transport settings
* per-tool approval policy

Schemas are **not persisted** in this file.

They are discovered at startup.

---

# Internal Tool Policy

New config file:

```
internal_tools.json
```

Purpose:

* store approval policy for internal tools.

Example:

```
tools:
  route_node:
    approval: auto
```

Internal tools default to **auto approval**.

---

# Tool Descriptor Model

All tools now share a unified descriptor model.

Fields include:

* provider_kind
* tool_name
* description
* parameters (schema)
* approval_mode
* handler

Two provider types exist:

| Provider | Source                 |
| -------- | ---------------------- |
| MCP      | external servers       |
| local    | internal runtime tools |

---

# Runtime Tool Approval System

Tool calls now pass through a unified approval gate.

Approval modes:

| Mode | Behavior              |
| ---- | --------------------- |
| auto | execute immediately   |
| ask  | request user approval |
| deny | reject execution      |

Approval requests pause the runtime.

---

# Inline Approval UI

Approval requests appear inside the chat UI.

Features:

* stacked tool-call display
* inline actions:

  * approve once
  * deny once
  * always allow
  * always deny
* persistent policy updates
* no modal dialogs

---

# Tool Call UI Improvements

Tool calls are now grouped into stacks.

Collapsed view:

```
Tools used (3)
```

Expanded view shows:

* each tool call
* arguments
* results
* approval status

---

# Approval Bug Fix

Earlier versions produced duplicate windows due to WebEngine navigation.

Fix:

* override `QWebEnginePage.createWindow()`
* block secondary page creation
* keep approvals inline only

---

# MCP Config UI Simplification

The config dialog now shows only:

* tool name
* availability
* approval selector

Tool schemas are hidden from the UI.

Schemas remain accessible internally for prompts.

---

# Internal Tools

Internal tools now participate in the same approval system.

Examples include:

* chat_history_tail
* world_apply_ops
* context_apply_ops
* route_node
* reflect_complete

Their schemas are defined in code.

---

# Runtime Node Architecture

Current nodes:

| Node            | Role                                 |
| --------------- | ------------------------------------ |
| context_builder | reconstruct working context          |
| reflect         | extract topics and memory candidates |
| answer          | generate final response              |

Future nodes:

| Node     | Planned Role            |
| -------- | ----------------------- |
| planner  | plan multi-step tasks   |
| executor | perform tool operations |

---

# Tool Execution Flow

```
LLM output
  ↓
tool loop
  ↓
approval gate
  ↓
tool handler
  ↓
result returned to node
```

Both MCP and internal tools use the same path.

---

# Summary

Recent work introduced:

* multi-server MCP support
* unified tool descriptor model
* runtime tool approval system
* stacked tool UI
* inline approval actions
* internal tool policy system

The system is now ready for:

* multi-server use
* planner/executor architecture
* prompt tuning and stabilization.
