---
title: pi RPC — Signal Mapping & Implementation Plan
type: plan
created: 2026-06-22
updated: 2026-07-03
status: historical
---

# pi RPC ↔ llm-thalamus UI Signal Mapping

## Signals to Keep

| UI Signal | pi RPC Source | Status |
|-----------|--------------|--------|
| assistant_stream_start | turn_start / message_start | ✅ Keep |
| assistant_stream_delta | message_update.text_delta | ✅ Keep |
| assistant_stream_end | message_end | ✅ Keep |
| thinking_started | message_update.thinking_start | ✅ Keep |
| thinking_delta | message_update.thinking_delta | ✅ Keep |
| thinking_finished | message_update.thinking_end | ✅ Keep |
| busy_changed | agent_start / agent_end | ✅ Keep |
| error | auto_retry_end failure | ✅ Keep |
| history_turn | get_messages response | ✅ Keep |
| activity_event (tool) | tool_execution_start/end | ✅ Keep, simplified |

## Signals to Drop

assistant_message (legacy), log_line, world_committed/updated, state_updated, prompt_*, tool_approval_requested

## PiRPCBridge Signals (implemented)

| Signal | Signature | Source Event |
|--------|-----------|-------------|
| `assistant_stream_start` | `Signal()` | `turn_start` / `message_start` |
| `assistant_stream_delta` | `Signal(str)` | `message_update` → `text_delta` |
| `assistant_stream_end` | `Signal()` | `message_end` |
| `thinking_started` | `Signal()` | `message_update` → `thinking_start` |
| `thinking_delta` | `Signal(str)` | `message_update` → `thinking_delta` |
| `thinking_finished` | `Signal()` | `message_update` → `thinking_end` |
| `tool_execution_start` | `Signal(str, str, dict)` | `tool_execution_start` |
| `tool_execution_update` | `Signal(str, str)` | `tool_execution_update` |
| `tool_execution_end` | `Signal(str, str, str, bool)` | `tool_execution_end` |
| `busy_changed` | `Signal(bool)` | `agent_start` / `agent_end` |
| `error` | `Signal(str)` | `auto_retry_end` failure |
| `history_turn` | `Signal(str, str, str)` | `get_messages` response |
| `response_received` | `Signal(str, object)` | `response` events |
| `compact_start` | `Signal(str)` | `compaction_start` |
| `compact_end` | `Signal(str, object)` | `compaction_end` |

### Notes

- `thinking_started/delta/finished` — dims/brightens the brain graphic. Thinking text display in chat renderer (inline thinking blocks) is partial — streaming thinking text is rendered during live turns.
- `tool_execution_*` — wired and rendered: tool cards with expandable per-item bodies, streaming summaries during execution, args summary with fallback chain, output preview in header.
- `compact_*` — no UI feedback for compaction events yet.

## Session Management

| Action | Method |
|--------|--------|
| Auto-resume last session | `bridge.start(resume=True)` → passes `-c` to pi |
| Load specific session | `bridge.start(session_path=path)` → passes `--session` to pi, or `switch_session` RPC |
| Start fresh | `{"type": "new_session"}` RPC |
| Get info | `{"type": "get_state"}` RPC |
| Fork | `{"type": "fork", "entryId": "..."}` RPC |
| Clone | `{"type": "clone"}` RPC |

Session files live at `~/.pi/agent/sessions/` (or inside the custom pi-config dir when using `--local`).

## Command Registry

Built-in RPC commands: model, new, compact, fork, clone, name, export, abort
Pi commands: discovered via get_commands on startup

## CLI Flags

| Flag | Effect |
|------|--------|
| *(none)* | Installed-mode graphics, default pi config |
| `--dev` | Repo-relative graphics, default pi config |
| `--local` | Installed-mode graphics, custom local-only pi config |
| `--dev --local` | Repo-relative graphics + custom local-only pi config |

## Dependencies

- Python 3.11+ (runtime)
- PySide6 6.11+ (Qt UI, pacman: python-pyside6)
- KaTeX (LaTeX rendering, pacman: katex)
- pi-coding-agent 0.79+ (backend, AUR: pi-coding-agent)
