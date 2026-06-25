# Renderer Debug Session — Archived

*This document captured the state of a renderer bug-hunting session on
2026-06-25.  The core issues identified here (tool/thinking ordering in
history, streaming event ordering, intermediate text in raw bubbles) were
fixed in the same session.  The "raw" bubble concept was replaced with
"agent-work" bubbles.  See `renderer-spec.md` for the current design.*

---

## Problem Statement

The chat renderer (`src/ui/chat_renderer.py`) displays pi coding agent sessions in a Qt WebEngine view. The rendering has three bubble types:
- **user** — the human's messages
- **assistant** — the agent's final text replies
- **raw** — everything else (thinking blocks, tool calls, intermediate text)

The goal: user and assistant messages in their own styled bubbles; all internal dialog (thinking, tool calls, intermediate text the agent says between actions) in unformatted raw-text bubbles between them.

## Current Architecture

### ChatRenderer (QWidget)
- `_messages` — flat list of message dicts, each with a `kind` field
- Data model methods: `add_turn()`, `add_thinking()`, `upsert_tool_event()`, etc.
- Streaming: `begin_assistant_stream()` → `append_assistant_delta()` → `end_assistant_stream()`
- Render: `end_assistant_stream()` calls `_request_render()` (deferred via `QTimer.singleShot(0)`) instead of direct `_render()` — avoids race with tool events that arrive after `message_end`

### messages_to_html() — Pure function rendering
Processes `_messages` in order: thinking/tool_stack/activity → raw buffer; turns → flush raw buffer then render bubble.

### _collect_raw_text()
Extracts text from thinking blocks, tool_stacks, and activity messages for the raw bubble. Currently processes in chronological order as messages appear in `_messages`.

### Key signal in main_window.py
`_on_tool_start()` in `src/ui/main_window.py` sets `self._streaming = False` — this closes the current text block so that the next text delta creates a fresh assistant turn. This is how we split assistant messages at tool boundaries.

## What Works

- Basic rendering: user bubbles, assistant bubbles (with markdown), raw text bubbles
- Tool calls in raw bubbles between assistant text blocks
- `_request_render()` deferred render avoids `setHtml()` race with late tool events
- `_streaming = False` in `_on_tool_start()` correctly splits text at tool boundaries

## What's Still Wrong

### 1. Order within raw bubbles — tool before thinking
The RPC event stream from pi delivers `tool_execution_start` BEFORE the subsequent `thinking_start`. Both end up in the same raw bubble in `_messages`, but the tool data appears before the thinking text. The `_collect_raw_text` function processes messages in `_messages` order, so the tool comes first.

**Attempted fix (reverted):** Sort all thinking before all tool_stacks in `_collect_raw_text`. This was wrong because it also moved post-tool thinking before the tool.

**Attempted fix (current):** In `_collect_raw_text`, detect when a `kind="thinking"` message is immediately followed by a `kind="tool_stack"` message, and emit the thinking first. This only works for actual `thinking` blocks, not for intermediate assistant text blocks (`kind="turn"`) that also end up in the raw bubble.

**Remaining issue:** Intermediate assistant text blocks (the agent's preliminary statements between tool calls) are `kind="turn"` messages. When `_streaming = False` splits them into separate turns, they land in the raw buffer but `_collect_raw_text` doesn't extract their content (no `kind == "turn"` handler). The text still appears in the raw bubble via a different code path, but the ordering fix doesn't apply.

### 2. Tool calls before intermediate text (the SINGLE_TOOL_TEST pattern)
The test pattern of text→tool→text→tool→text shows tool calls appearing before the text that follows them in the raw bubble. This happens because tool_stack messages land in `_messages` between the turn messages, and the raw bubble collects them in order.

### 3. Last tool call timing
On app restart, tool calls from history are sometimes missing. The `_request_render()` deferred render helps but doesn't fully solve it. Suspect a race between `QTimer.singleShot(0)` and the bridge's RPC event processing.

## Open Questions

1. **How should intermediate assistant text be rendered?** When a single assistant message has text→tool→text→tool→text blocks, the streaming generates separate turns at each tool boundary. Should the intermediate texts go into the raw bubble (with tools) or be separate assistant bubbles?

2. **How does the TUI handle this?** pi's built-in TUI likely has a reference ordering. The RPC docs describe `turn_start`/`turn_end`, `message_start`/`message_end`, and content block boundaries (`text_start/end`, `thinking_start/end`, `toolcall_start/end`) — the TUI may use these to properly sequence blocks within a turn.

3. **Should `_collect_raw_text` handle `kind="turn"`?** If intermediate assistant texts go into the raw bubble, `_collect_raw_text` needs a handler for `turn` messages. If they should be separate assistant bubbles, the `_streaming = False` split and the simple per-turn rendering already does this — the tools between them go into raw bubbles.

## Files Involved

- `src/ui/chat_renderer.py` — Main renderer (1380 lines)
  - `messages_to_html()` (line ~702) — rendering loop
  - `_collect_raw_text()` (line ~567) — raw text extraction
  - `_request_render()` (line ~1115) — deferred render
  - `begin_assistant_stream()` (line ~1064) — turn creation
  - `end_assistant_stream()` (line ~1091) — turn finalization
  - `upsert_tool_event()` (line ~986) — tool stack management
- `src/ui/main_window.py` — Signal wiring
  - `_on_tool_start()` (line ~362) — sets `_streaming = False`
  - `_on_thinking_started()` (line ~347) — does NOT set `_streaming` (was reverted)
  - `_on_stream_delta()` (line ~336) — handles text deltas
- `src/controller/pi_bridge.py` — RPC event handling
  - `_route_message_update()` — routes `message_update` events
  - `_emit_structured_history()` — history loading

## Testing Pattern

Run the test pattern in the app to verify ordering:
1. "First text block."
2. Tool: `echo "MARKER_1"`
3. "Second text block."
4. Tool: `echo "MARKER_2"`
5. "And final answer."

Expected render order:
```
[asst] "First text block."
[raw]  [bash] MARKER_1
[asst] "Second text block."
[raw]  [bash] MARKER_2
[asst] "**And final answer.**"
```