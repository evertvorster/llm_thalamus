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

## Dependencies

| Dependency | Version | For | Install (Arch) |
|-----------|---------|-----|----------------|
| PySide6 | 6.11+ | Qt UI framework | `pacman -S python-pyside6` |
| KaTeX | — | LaTeX rendering in chat | `pacman -S katex` |
| pi-coding-agent | 0.79+ | Backend runtime via RPC | AUR (`pi-coding-agent`) |
| Python | 3.11+ | Runtime | `pacman -S python` |

## Dev vs Installed Mode

The entry point (`src/llm_thalamus.py`) accepts a `--dev` flag that changes two paths:

| Resource | Dev mode | Installed mode |
|----------|----------|----------------|
| pi config dir | `./resources/pi-config/` | `/usr/share/llm-thalamus/pi-config/` |
| Graphics | `./resources/graphics/` | `/usr/share/llm-thalamus/graphics/` |

```python
def resolve_paths(dev_mode: bool):
    if dev_mode:
        pi_config = Path("resources/pi-config/")
        graphics  = Path("resources/graphics/")
    else:
        pi_config = Path("/usr/share/llm-thalamus/pi-config/")
        graphics  = Path("/usr/share/llm-thalamus/graphics/")
    return pi_config, graphics
```

The AUR package installs:
- Python sources to `/usr/lib/llm-thalamus/`
- pi config + graphics to `/usr/share/llm-thalamus/`
- Launcher to `/usr/bin/llm-thalamus`

## Implementation Plan

### Phase 1: Spike
1. Create `resources/pi-config/` (models.json, settings.json, agents/)
2. Write `src/controller/pi_bridge.py` (PiRPCBridge)
3. Write minimal `src/llm_thalamus.py` entry point (--dev flag, path resolution, spawn bridge + window)
4. Test — send a prompt, verify events stream

### Phase 2: Core UI
5. Import chat_renderer.py, widgets.py (unchanged)
6. Rewrite `src/ui/main_window.py` — connect PiRPCBridge signals to chat renderer
7. Build session picker dialog
8. Startup flow — list sessions or resume most recent

### Phase 3: Polish
9. /-command palette — get_commands + Qt autocomplete
10. Brain animation, error handling, restart on pi crash
11. Model switching from UI

## Files to Keep

```
src/ui/chat_renderer.py          (unchanged)
src/ui/widgets.py                (unchanged)
resources/graphics/              (brain images)
pi-rpc-integration.md            (this doc)
rpc-signal-mapping.md            (technical blueprint)
```

## Files to Rewrite

```
src/ui/main_window.py            (connect PiRPCBridge, strip obsolete signals)
src/llm_thalamus.py              (new entry point with --dev mode)
src/controller/pi_bridge.py      (NEW — PiRPCBridge class)
Makefile                         (install paths for AUR)
```

## Files to Delete (done on pi-rpc-bridge branch)

All LangGraph backend, stale config, tests, and root-level artifacts — 120+ files removed. Preserved on `main` branch.
