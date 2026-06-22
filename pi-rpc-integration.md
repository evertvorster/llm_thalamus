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

**CLI flags:**

| Flag | Effect |
|------|--------|
| *(none)* | Installed-mode graphics, default pi config (`~/.pi/agent/`) |
| `--dev` | Repo-relative graphics, default pi config |
| `--local` | Installed-mode graphics, custom local-only pi config |
| `--dev --local` | Repo-relative graphics, custom local-only pi config |

**Path resolution:**

| Resource | Dev mode | Installed mode |
|----------|----------|----------------|
| Graphics | `./resources/graphics/` | `/usr/share/llm-thalamus/graphics/` |
| pi config (with `--local`) | `./resources/pi-config/` | `/usr/share/llm-thalamus/pi-config/` |
| pi config (no `--local`) | Uses `~/.pi/agent/` (default) | Uses `~/.pi/agent/` (default) |

When `--local` is active, the startup sequence also sends a `set_model` RPC
command to select Gemma 4 E2B from the llama-cpp provider.  Without `--local`,
pi uses whatever model the user has configured in their normal pi setup.

## Implementation Status

### ✅ Phase 1: Spike (complete)

| Task | File | Status |
|------|------|--------|
| pi config dir | `resources/pi-config/` | ✅ models.json (llama-cpp only, 3 BF16 models), settings.json |
| PiRPCBridge | `src/controller/pi_bridge.py` | ✅ 311 lines, 15 Qt signals, reader thread, event routing |
| Entry point | `src/llm_thalamus.py` | ✅ 211 lines, --dev flag, path resolution, MainWindow with 11 signal connections |
| Test | Manual verification | ✅ pi spawns, model selects, prompts respond |

**Key learnings from Phase 1:**
- pi does not auto-select a model — must call `set_model` RPC on startup
- BrainWidget defaults to `"inactive"` (dark) — must set to `"thalamus"` initially
- `resources/pi-config/` must exist before pi starts, else pi has no models
- Pi's default ~/.pi/agent/ config (with DeepSeek) is separate; llm-thalamus only sees local models

### 🔜 Phase 2: Core UI

| Task | Status | Notes |
|------|--------|-------|
| Extract MainWindow to src/ui/main_window.py | ✅ | Extracted 2026-06-22, 163 lines |
| Session picker dialog | 🔜 | List ~/.pi/agent/sessions/, load with switch_session |
| Startup flow — resume or pick | 🔜 | Currently starts fresh every time |
| Tool call display in chat | ✅ | Already wired via tool_execution_start/end signals |
| Error handling, pi crash recovery | 🔜 | bridge.shutdown + restart on crash |

### 🔜 Phase 3: Polish

| Task | Status |
|------|--------|
| /-command palette (get_commands + Qt autocomplete) | 🔜 |
| Brain animation for thinking | 🔜 |
| Model switching from UI | 🔜 |

## Files on pi-rpc-branch Branchn

```
src/controller/pi_bridge.py      (311 lines — PiRPCBridge)
src/llm_thalamus.py              (211 lines — entry point with MainWindow)
src/ui/chat_renderer.py          (1288 lines — kept from original)
src/ui/widgets.py                (789 lines — kept from original)
resources/pi-config/models.json  (local-only model definitions)
resources/pi-config/settings.json
resources/graphics/              (4 brain images)
pi-rpc-integration.md            (this doc)
rpc-signal-mapping.md            (technical blueprint)
```

## Files Deleted (on pi-rpc-bridge branch)

All LangGraph backend, stale config, tests, and root-level artifacts — 120+ files removed. Preserved on `main` branch.
