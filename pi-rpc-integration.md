---
title: pi RPC Integration — Mission & Direction
type: mission
created: 2026-06-22
updated: 2026-06-22
status: active
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
| pi config dir | `resources/pi-config/` | ✅ models.json, settings.json |
| PiRPCBridge | `src/controller/pi_bridge.py` | ✅ 311 lines, 15 Qt signals, reader thread, event routing |
| Entry point | `src/llm_thalamus.py` | ✅ --dev/--local flags, path resolution |
| MainWindow | `src/ui/main_window.py` | ✅ Extracted, 163 lines, 11 signal connections |
| Session resume | `bridge.start(resume=True)` | ✅ Auto-resumes last session via `-c` |
| Missing event routing | `pi_bridge.py` | ✅ message_start, turn_end, text_start/end, extension_ui_request |
| `--local` flag | `llm_thalamus.py` | ✅ Optional custom pi config for local-only models |

**Key learnings:**
- pi does not auto-select a model — must call `set_model` RPC on startup
- BrainWidget defaults to `"inactive"` (dark) — must set to `"thalamus"` initially
- Default mode uses `~/.pi/agent/` (user's normal pi setup with DeepSeek)
- `--local` mode uses the shipped pi-config with llama-cpp only

### 🔜 Next Up

See the Obsidian vault at `Projects/Programming/llm-thalamus/next-features-brainstorm.md` for detailed brainstorming on:
- Session list panel
- Full history rendering (thinking blocks inline)
- Status bar (token counts, model, MemPalace stats)
- Interrupt/abort button
- Real-time thinking display during streaming
- Model switching from UI
- Brain click debug viewer

## Files on pi-rpc-bridge Branch

```
src/controller/pi_bridge.py      (311 lines — PiRPCBridge)
src/llm_thalamus.py              (64 lines — entry point)
src/ui/main_window.py            (163 lines — MainWindow)
src/ui/chat_renderer.py          (1288 lines — kept from original)
src/ui/widgets.py                (789 lines — kept from original)
resources/pi-config/models.json  (local-only model definitions)
resources/pi-config/settings.json
resources/graphics/              (4 brain images)
pi-rpc-integration.md            (this doc)
rpc-signal-mapping.md            (technical blueprint)
.gitignore
LICENSE.md
README.md
```

## Files Deleted (on pi-rpc-bridge branch)

All LangGraph backend, stale config, tests, and root-level artifacts — 120+ files removed. Preserved on `main` branch.
