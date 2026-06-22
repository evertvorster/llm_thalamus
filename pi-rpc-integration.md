---
title: pi RPC Integration — Mission & Direction
type: mission
created: 2026-06-22
updated: 2026-06-22
status: draft
---

# Mission: llm-thalamus as a Rich Qt Frontend for pi

## Vision

llm-thalamus becomes a **rich Qt desktop GUI for the pi coding agent**. pi is the runtime (sessions, models, subagents, tools, memory). llm-thalamus is the window into it.

```
┌──────────────────────────────────────────────────────────┐
│                    llm-thalamus (Qt)                      │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Session picker     Chat display    Brain widget   │  │
│  │  /-command palette  (LaTeX, code,   (animation)    │  │
│  │                     thinking, tools)                │  │
│  └────────────────────────────────────────────────────┘  │
│                         │ stdin/stdout JSONL              │
│                         ▼                                │
│  ┌────────────────────────────────────────────────────┐  │
│  │              pi --mode rpc (subprocess)             │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Sessions  ·  Models  ·  Subagents  ·  Tools  │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
│                         │                                │
│                         ▼                                │
│               llama.cpp server (BeeLlama)                │
└──────────────────────────────────────────────────────────┘
```

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Session model | pi's native sessions | Session management, compaction, branching are pi's job. llm-thalamus uses switch_session. |
| /resume missing from RPC | Read session dir directly | List ~/.pi/agent/sessions/ from Qt, call switch_session. |
| Commands palette | get_commands RPC + Qt autocomplete | Discover commands dynamically, show in / dropdown. |
| Model config | PI_CODING_AGENT_DIR | Ship default config with local models. User can swap. |
| UI framework | PySide6 Qt | Unique in pi ecosystem (others use Electron/Tauri). |

## What pi gives us

Subagent dispatch, streaming text & thinking, tool execution, session management, MemPalace, model switching, commands & extensions.

## What llm-thalamus provides

Rich message rendering (LaTeX, code blocks), session browser, brain animation, /-command palette. Future: voice I/O, inline graphics.

## Slash Commands

**Tier 1** — Dedicated RPC commands: set_model, new_session, switch_session, fork, clone, compact, abort, export_html, get_session_stats, set_session_name, get_messages, set_thinking_level.

**Tier 2** — Sent as prompts: extension commands (/mycommand), prompt templates (/review), skills (/skill:name).

**Discovery:** get_commands RPC lists all tier-2 commands.

## Implementation Plan

### Phase 1: Spike
1. Create resources/pi-config/ (models.json, settings.json, agents/)
2. Write PiRPCBridge — spawn pi --mode rpc, read JSONL, emit Qt signals
3. Test with minimal window

### Phase 2: Core UI
4. Import chat_renderer.py, widgets.py
5. Rewrite main_window.py — connect bridge, strip obsolete signals
6. Build session picker
7. Startup flow

### Phase 3: Polish
8. /-command palette
9. Brain animation, error handling
10. Model switching

## Files to Keep

src/ui/chat_renderer.py, src/ui/widgets.py, resources/graphics/

## Files to Rewrite

src/ui/main_window.py, src/llm_thalamus.py

## Files to Delete (done)

src/runtime/, src/config/, src/controller/mcp/, src/controller/world_state.py, src/controller/runtime_services.py, src/controller/worker.py, src/controller/chat_history*.py, src/controller/internal_tools/config.py, src/tests/, src/ui/config_dialog.py, resources/config/, resources/Documentation/, resources/prompts/, Makefile, llm_thalamus.desktop, INSTALL_NOTES.md, CONTRIBUTING.md, README_architecture.md, README_developer.md, context.md
