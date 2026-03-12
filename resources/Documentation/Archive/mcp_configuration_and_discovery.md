# Note
MCP tool schemas are discovered at startup and are not
persisted in the configuration file. The configuration file
stores expected servers, enabled tools, and approval policy.

Implemented on 2026-03-11.

# MCP Configuration, Discovery, Permissions, and UI

## llm_thalamus Architecture Design Note

---

# 1. Objective

Refactor MCP handling so that:

* MCP server definitions are split out of `config.json`
* MCP tool schemas are discovered at startup
* discovered tools are cached for the run
* per-tool permissions are persisted locally
* new tools default to `ask`
* runtime uses cached schema, not live rediscovery
* UI shows MCP server status and provides focused configuration access
* future live tool approval can update both memory and disk config

This design establishes a **deterministic MCP tool environment per run**, while allowing flexible configuration and approval policy.

---

# 2. Scope of This Work Step

This step should cover:

* config split
* startup discovery
* tool reconciliation
* persistent per-tool permission storage
* runtime use of cached schema
* main-window MCP status panel
* config UI for MCP servers and tool permissions

This step should **not** cover:

* full live approval popup implementation
* refresh/reconnect beyond normal startup discovery
* advanced schema diff handling
* multi-server edge-case polish
* destructive automatic migrations

---

# 3. Core Design Principles

## 3.1 Startup Is the Refresh Mechanism

For now:

* every startup interrogates configured enabled MCP servers
* discovered tools are reconciled into local config
* no separate refresh workflow is required yet

---

## 3.2 Tool Schema Is Fixed for the Run

Once startup discovery completes:

* runtime uses cached schema for the whole run
* nodes do not rediscover tool schema mid-turn
* tool usage stays deterministic inside the run

---

## 3.3 Separate Schema from Policy

Two different truths exist:

### Live Truth (Server)

What the server currently exposes via:

```
tools/list
```

### Local Truth (Client)

What this client allows for each tool:

* `ask`
* `auto`
* `deny`

These must remain separate.

---

## 3.4 New Tools Default to Ask

Whenever a new tool appears during startup discovery:

* add it to config
* set permission to `ask`

---

## 3.5 Missing Tools Are Never Deleted Automatically

If a tool disappears from discovery:

* keep the config entry
* mark `available = false`

This protects policy against:

* temporary server outages
* partial server upgrades
* intermittent tool failures

---

## 3.6 Runtime Registry Must Use Startup Cache

Nodes should operate only from:

* cached tool metadata
* cached approval mode

Nodes must **never rediscover tool schemas during execution**.

This ensures:

* deterministic behavior
* stable prompts
* consistent approval policy

---

# 4. MCP Configuration File

## 4.1 Dedicated Config File

New configuration file:

```
mcp_servers.json
```

Its location must be resolved using the **existing startup path resolution logic** used for:

* dev mode
* installed mode
* config/log/db/resource separation

No new path rules should be introduced.

---

# 5. Configuration Schema

## Example Structure

```json
{
  "servers": {
    "openmemory": {
      "label": "OpenMemory",
      "enabled": true,

      "transport": {
        "type": "streamable-http",
        "url": "http://localhost:8080/mcp",
        "headers": {}
      },

      "status": {
        "available": false,
        "last_startup_check": null,
        "last_error": null
      },

      "tools": {
        "openmemory_query": {
          "approval": "ask",
          "description": "Query OpenMemory for contextual memories",
          "input_schema": {},
          "available": false,
          "last_seen": null
        }
      }
    }
  }
}
```

---

# 6. Field Definitions

## 6.1 Server Identity

The map key is the **canonical server id**:

```
servers["openmemory"]
```

Rules:

* map key = stable server identifier
* `label` = UI display name
* runtime must reference server id, not label

---

## 6.2 Server Fields

Required:

* `label`
* `enabled`
* `transport`

Optional runtime-derived fields:

* `status.available`
* `status.last_startup_check`
* `status.last_error`

These fields are **diagnostic only**, not authoritative configuration.

---

## 6.3 Transport

Transport describes how the MCP server is contacted.

Examples:

### HTTP MCP

```json
"transport": {
  "type": "streamable-http",
  "url": "http://localhost:8080/mcp",
  "headers": {}
}
```

### stdio MCP

```json
"transport": {
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "openmemory-js", "mcp"],
  "env": {}
}
```

Future transports may be added.

---

## 6.4 Tool Fields

Each tool entry contains two conceptual domains.

### Policy

User-controlled:

```
approval
```

Possible values:

* `ask`
* `auto`
* `deny`

---

### Discovered Snapshot

Information obtained from the MCP server:

* `description`
* `input_schema`
* `available`
* `last_seen`

The raw `input_schema` returned by the server should be preserved as faithfully as possible.

---

# 7. Startup Discovery and Reconciliation

## 7.1 Startup Flow

For every enabled MCP server:

1. load server config

2. attempt connection

3. call `tools/list`

4. collect discovered tools:

   * `name`
   * `description`
   * `inputSchema`

5. reconcile against local tool map

6. update runtime registry

7. persist config if changed

---

## 7.2 Reconciliation Rules

### Known Tool Still Present

```
keep approval
update description
update input_schema
available = true
last_seen = now
```

---

### New Tool Discovered

```
create config entry
approval = ask
store description
store input_schema
available = true
last_seen = now
```

---

### Tool Missing From Discovery

```
keep config entry
available = false
```

Policy must **never be deleted automatically**.

---

## 7.3 Server Connection Failure

If connection fails:

```
status.available = false
status.last_error = error
```

Existing tool definitions remain unchanged.

---

# 8. Runtime Tool Registry

After startup reconciliation:

A runtime registry is built.

Each tool descriptor contains:

```
server_id
tool_name
description
input_schema
approval_mode
```

Nodes must operate from this registry.

---

# 9. OpenMemory First Vertical Slice

Initial MCP server:

```
openmemory
```

---

## 9.1 Tool Types

### Read / Query

* openmemory_query
* openmemory_list
* openmemory_get

### Mutating

* openmemory_store
* openmemory_reinforce
* openmemory_delete

---

## 9.2 Node Policy (Prompt Level)

### context_builder

Allowed:

```
read/query tools
```

### reflect

Allowed:

```
read/query
mutating tools
```

This restriction is handled via prompt design initially.

---

# 10. Legacy OpenMemory Cleanup

Previous versions included **non-MCP OpenMemory initialization**.

These remnants must be inspected.

---

## What to Look For

* old startup hooks
* old connection checks
* old tool registration logic
* old config handling
* hardcoded OpenMemory initialization

---

## What to Do

Each remnant should be classified as:

```
delete
reuse
replace
```

---

## Desired End State

```
OpenMemory becomes a normal MCP server
```

No special initialization path should remain.

---

# 11. UI Design

Two MCP UI surfaces will exist.

---

# 11.1 Main Window MCP Panel

Location:

```
between brain graphic
and world state display
```

Panel title:

```
MCP servers
```

Purpose:

* show connection state
* show number of discovered tools
* allow navigation to config UI

---

## Example Rows

Connected:

```
OpenMemory   ● connected   6 tools
```

Unavailable:

```
OpenMemory   ○ unavailable
```

Disabled:

```
OpenMemory   – disabled
```

---

## Interaction

Clicking a row opens the MCP config UI focused on that server.

---

# 11.2 MCP Config UI

Accessible via:

```
Config → MCP Servers
```

Two modes:

### All Servers Mode

Manage multiple servers.

### Focused Mode

Open directly for one server from main window.

---

## Capabilities

* add server
* edit transport
* display discovered tools
* edit per-tool permission

---

# 12. Tool Permission UX

Each tool exposes:

```
ask
auto
deny
```

---

## Config Screen Behavior

User can change permission at any time.

Changes should be written immediately to disk.

---

# 13. Future Runtime Approval Integration

Later implementation will allow runtime tool approval popups.

When a decision is made:

```
update runtime permission
write change to disk
```

This keeps policy synchronized.

---

# 14. Implementation Phases

## Phase 0 — Inspection

Inspect:

* startup path resolution
* config load/save paths
* MCP registration path
* legacy OpenMemory code
* UI insertion points

Deliverable:

inspection report.

---

## Phase 1 — Config Split

Implement:

* `mcp_servers.json`
* loader/saver
* migrate OpenMemory definition

---

## Phase 2 — Startup Discovery

Implement:

* MCP server interrogation
* tools/list discovery
* reconciliation rules
* persist updated config

---

## Phase 3 — Runtime Registry

Implement:

* runtime tool registry
* approval mode enforcement
* no mid-run rediscovery

---

## Phase 4 — MCP Status Panel

Implement:

* MCP servers panel
* status display
* navigation to config UI

---

## Phase 5 — Config UI

Implement:

* server editing
* tool listing
* permission editing

---

## Phase 6 — Runtime Approval Sync

Future feature:

* approval popup
* policy persistence

---

# 15. Key Invariants

1. MCP config uses existing dev/installed path logic.
2. Startup discovery is the only refresh mechanism.
3. Tool schema is fixed for the run.
4. New tools default to `ask`.
5. Known tools retain their permission.
6. Missing tools are not deleted automatically.
7. Runtime uses cached schema.
8. Runtime approval changes must update disk.
9. Main window MCP panel is status/navigation only.
10. Editing occurs only in the config UI.

---

# 16. First Implementation Slice

Smallest vertical slice:

1. inspect startup paths
2. create/load `mcp_servers.json`
3. migrate `openmemory` definition
4. interrogate OpenMemory server
5. discover tools
6. store them in config
7. default new tools to `ask`
8. log reconciliation results

UI work comes later.

---

# 17. Recommended Codex Session Prompt

```
We are implementing MCP configuration refactoring in llm_thalamus.

Important context:
- The app supports dev mode and installed mode with different paths.
- Startup already resolves paths for config/log/db/resources.
- There may be remnants of older non-MCP OpenMemory initialization.
- Startup discovery is the only refresh mechanism.
- MCP tool schemas should be discovered at startup and fixed for the run.
- New tools default to ask.
- OpenMemory is the first MCP server.

Please inspect and report:

1. startup path resolution
2. config load/save logic
3. where mcp_servers.json should live
4. current MCP registration path
5. legacy OpenMemory remnants
6. best startup hook for discovery
7. where config writes occur
8. where UI MCP panel should attach

Do not modify code yet.

Produce:
- files involved
- startup/config flow
- legacy OpenMemory findings
- proposed file touch order
- smallest safe first implementation slice
```
