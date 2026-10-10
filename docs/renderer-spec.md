# Chat Renderer — Inputs & Features

## Data Inputs

The renderer receives data from exactly two pipelines. Both ultimately deliver the
same data shapes — the internal model does not distinguish source.

### Source A — Session files (history)

Pi stores sessions as JSONL files at `~/.pi/agent/sessions/<scope>/<id>.jsonl`.
Each line is a self-contained JSON object.  The relevant entry type is:

```json
{"type": "message", "message": AgentMessage}
```

**AgentMessage** shapes:

| Role | Content field | Extra fields |
|------|--------------|-------------|
| `"user"` | `[{"type":"text", "text":"..."}]` | `timestamp` |
| `"assistant"` | `[{type:"thinking",...}, {type:"text",...}, {type:"toolCall",...}]` | `provider`, `model`, `usage`, `stopReason`, `timestamp`, `responseId` |
| `"toolResult"` | `[{"type":"text", "text":"..."}]` | `toolCallId`, `toolName`, `isError`, `details`, `timestamp` |
| `"bashExecution"` | — | `command`, `output`, `exitCode`, `timestamp` |

**Assistant content block types:**

| Block type | Fields |
|-----------|--------|
| `"thinking"` | `thinking` (text), `thinkingSignature` |
| `"text"` | `text` (markdown) |
| `"toolCall"` | `id` (call_id), `name` (tool name), `arguments` (dict or JSON string) |

A single `assistant` message may interleave multiple blocks — e.g. thinking, then
text, then several toolCalls, then more thinking, then more text.

**Tool result content** is an `[{"type":"text","text":"..."}]` array containing
the tool's stdout / response. The `isError` flag indicates failure. The
`details` dict may contain structured subagent result metadata.

`bashExecution` messages represent pre-prompt bash commands and are not
UI-relevant for history display.

### Source B — Live RPC events (streaming)

Pi sends JSONL events over stdout when started with `pi --mode rpc`.  The events
relevant to rendering are:

| Event | Payload | Meaning |
|-------|---------|---------|
| `agent_start` | — | Agent begins processing a prompt |
| `agent_end` | `messages: [...]` | Agent completed; carries all generated messages |
| `turn_start` | — | New assistant turn begins |
| `turn_end` | `message: {...}`, `toolResults: [...]` | Turn completed |
| `message_update` | `assistantMessageEvent: {...}` | Streaming delta from the assistant |
| `message_end` | — | Assistant message complete |
| `tool_execution_start` | `toolCallId`, `toolName`, `args` (dict) | Tool begins execution |
| `tool_execution_update` | `toolCallId`, `partialResult` (content array) | Streaming progress from running tool |
| `tool_execution_end` | `toolCallId`, `toolName`, `result` (content array), `isError`, `details` | Tool finished |
| `response` (command=`get_messages`) | `data.messages` (AgentMessage array) | Full session history |

**Streaming deltas** (`message_update.assistantMessageEvent`):

| Delta type | Field | Meaning |
|-----------|-------|---------|
| `text_start` / `text_end` | `contentIndex` | Content block boundaries |
| `text_delta` | `delta` | Text chunk — append to current assistant bubble |
| `thinking_start` / `thinking_end` | — | Thinking block boundaries |
| `thinking_delta` | `delta` | Thinking text chunk — append to thinking bubble |
| `toolcall_start` / `toolcall_end` | — | In-message tool call announcement |
| `done` | `reason` | Message complete (`"stop"`, `"length"`, `"toolUse"`) |
| `error` | `reason` | Stream error (`"aborted"`, `"error"`) |

**Tool execution progress** (`tool_execution_update.partialResult`):
- `content`: `[{"type":"text","text":"..."}]` — accumulated output so far (not just the delta)

**History loading** (`get_messages` response):
The `data.messages` array contains the full AgentMessage list in conversation
order.  Tool results are matched to their `toolCall` blocks by `toolCallId` and
emitted as paired `tool_execution_start` / `tool_execution_end` signals so the
renderer builds proper tool stacks.

### Internal message model

Regardless of source, all data lands in a flat list of message dicts.  Each
dict carries a `kind` field that determines how it renders:

| `kind` | Required fields | Optional | Meaning |
|--------|----------------|----------|---------|
| `"turn"` | `role` (`"human"` or `"you"`), `content` (markdown string) | `meta` (timestamp label) | A user or assistant speech bubble |
| `"thinking"` | `text` (plain string) | `expanded` (bool, default false) | A collapsible reasoning block |
| `"tool_stack"` | `stack_id` (string, matches toolCallId), `items` (list of item dicts) | `expanded` (bool) | A container for one tool execution |
| `"activity"` | `content` (string) | `meta` | Legacy system message |

**Tool stack item** fields:

| Field | Type | Description |
|-------|------|-------------|
| `tool_call_id` | string | Matches the pi `toolCallId` |
| `tool_name` | string | e.g. `"bash"`, `"read"`, `"mempalace_search"` |
| `status` | string | One of: `"running"`, `"ok"`, `"error"`, `"denied"`, `"pending_approval"` |
| `args` | dict | Raw structured arguments (e.g. `{"command": "ls -la"}`) |
| `_fmt_args` | string | HTML-escaped formatted arguments for the expanded view |
| `_fmt_result` | string | HTML-escaped formatted result for the expanded view |
| `_fmt_stream` | string | HTML-escaped streaming partial text (during live execution) |
| `_fmt_details` | string | Formatted subagent result metadata |
| `result` | any | Raw result value |
| `error` | string | Error message if `status == "error"` |
| `expanded` | bool | Whether the item body is expanded (default false) |
| `item_key` | string | Unique key within the stack (usually `tool_call_id`) |
| `item_kind` | string | `"tool"` (default) or `"node"` |
| `tool_kind` | string | Optional: `"mcp"` |
| `mcp_server_id` | string | Optional: MCP server identifier |
| `request_id` | string | For `pending_approval`: the approval request ID |
| `description` | string | For `pending_approval`: human-readable description |
| `step` | int | Optional: step number within a multi-step operation |

---

---

## Features

### 0. Architecture

The file is split into two layers:

1. **Pure functions** — module-level functions with no Qt imports.
   Convert `_messages[]` slices into inner HTML.  All rendering logic
   lives here.

2. **`ChatRenderer(QWidget)`** — thin wrapper around `QWebEngineView`.
   Owns `_messages[]`, manages the render cycle, bridges HTML↔Python
   via `thalamus://` URLs.

The data model is a flat `_messages[]` list of dicts, each with a `kind`
field: `"turn"`, `"thinking"`, `"tool_stack"`, or `"activity"`.  All data
sources (session history and live RPC streaming) converge into this list.

### 1. Message rendering

The renderer must produce HTML for every message kind in the internal model.

Note: thinking blocks and tool stacks are not bubbles of their own.  They
render **inside** the icon strip's detail, or in a standalone agent-work bubble
for a turn with no reply — see §2 for where they appear.

#### 1.1 Turns

- User messages appear as **left-aligned blue bubbles**.
- Assistant messages appear as **right-aligned white bubbles**.
- Content is rendered through a **markdown pipeline**: fenced code blocks get
  syntax-highlighting placeholders; the rest goes through standard CommonMark
  with table support.
- An optional **meta label** (timestamp) appears above the bubble content in
  small gray text.
- The **last assistant bubble** in the rendered view receives a visual highlight
  (colored border glow).
- During live streaming, the assistant bubble gets a **stable DOM ID** so
  JavaScript can append plain-text deltas without a full re-render.

#### 1.2 Thinking blocks

- Rendered as **collapsible cards** with a purple-tinted background.
- The header reads "Thinking" with a ▼/▶ indicator; clicking it toggles the block.
- **Collapsed by default.**  While a turn is streaming the newest thinking block
  stays open (see §2).
- Clicking the toggle manipulates the DOM directly — no full page reload.

#### 1.3 Tool stacks

A tool stack represents one tool execution (identified by `stack_id`, which is
the tool's `toolCallId`).  Some tools are multi-step (subagents) and produce
multiple items within one stack.  By far the common case is a single item.

- Rendered as cards, always **right-aligned**.  Where they appear depends on
  the turn: inside the icon strip's detail when the turn has a reply (see §2),
  or in a standalone agent-work bubble when it does not.
- **Card header** shows the tool name and a one-line summary, with a ▼/▶
  indicator; clicking it toggles the card body.
- Card bodies are **hidden by default**.

#### 1.4 Tool stack items — collapsed state

When collapsed, each item shows a **compact one-line header**:

```
bash | ls -la → total 48 | complete
```

Components, left to right:
- **Title** — the tool name (bold).
- **Summary** — a human-readable preview of what the tool is operating on.
  Extracted from the structured `args` dict using per-tool field selectors
  (e.g. `bash→command`, `read→path`, `edit→path ← oldText`,
  `mempalace_search→query`, `subagent→task`).  Falls back to the formatted
  args/result if no structured args are available.  Truncated with CSS ellipsis.
- **Status badge** — colored pill (green = ok, red = error, purple = denied,
  orange = pending approval, blue-gray = running).  Label: "complete", "failed",
  "denied", "awaiting approval", "running".
- Optional **meta line** below the header showing item kind (`node`),
  `tool_kind` (`mcp`), `mcp_server_id`, and step number.

The summary must show **the actual command/path/query** — not escaped JSON,
not garbled HTML entities.  This is the user's primary signal for what the
tool is doing without expanding it.

#### 1.5 Tool stack items — expanded state

When expanded, the summary hides and the following sections appear:

- **Arguments** — label + `<pre>` block with formatted JSON (dark background,
  monospace font).  Uses the pre-escaped `_fmt_args`.
- **Output** — label + `<pre>` block with formatted result.  Uses `_fmt_result`
  (final) or `_fmt_stream` (live streaming partial).
- **Subagent details** — if `_fmt_details` is set, shows agent name, model,
  turn count, and token usage in a compact info line above Arguments.
- **Error message** — if `status == "error"` and `error` is set, shows the
  error text above Arguments.

#### 1.6 Approval

Tool approval is **not** rendered in the transcript.  A request arrives as an
extension UI request, which the main window raises as a Qt dialog
(`extension_ui_dialog` → the main window's handler), and the answer goes back
over RPC as `extension_ui_response`.  The transcript shows only that a tool is
`pending_approval`, as a status badge on the item.

### 2. Agent work: the icon strip

Thinking and tool calls are **not** shown as bubbles of their own.  A turn that
did work carries an **icon strip** in the top-right corner of its reply bubble,
directly under the Copy button:

```
🧠 3
⚙️ 12
⚠️ 1
```

One icon per category present, stacked vertically, each with a count.  Clicking
one opens that category's items inline, below the reply:

```
icon  →  list of items  →  the item's own body
```

Categories are **buckets**, not messages.  Each holds every item of that kind
from the turn, in arrival order.  A bucket is a *view* over the ordered
messages, not a copy of them — the data model keeps the real order, so nothing
is lost to the grouping.

The strip sits in padding reserved on the right of the bubble, and the bubble is
given a minimum height so a tall stack cannot overflow it.  The reserve does not
grow with the number of categories, because the icons stack vertically.

#### Collapse behaviour

Items are collapsed by default.  The exception is a **live tail**: while a turn
is streaming, the newest thinking block and the newest tool call stay open
until the next item of that type arrives, or until the reply starts — at which
point everything collapses and the work becomes the icon strip.  One rule
serves both the live view and the settled drill-down.

**Liveness is the turn, not the stream.**  The renderer takes it from the busy
signal (`set_turn_live`) as well as from open blocks, because a running tool has
no streaming block of its own: tool cards are keyed by `toolCallId` through
`upsert_tool_event`, and the main window forwards only `reply` and `thinking`
blocks to `begin_block`.  Deriving it from `_streaming_blocks` alone left a
running tool rendering collapsed — the tail stayed shut exactly while there was
something to watch.

Collapse state is **DOM-only**, toggled by CSS classes.  A full re-render resets
it to the default.

#### Nested tools

A `subagent` tool's own calls arrive in its result metadata as a flat list of
`{text, expandedText}` pairs — pi reports one level of nesting, never deeper.
They render indented under the subagent card, collapsed like any other item, and
the subagent's header carries the count (`Subagent: scout · 3 nested`) so that a
subagent does not read as an ordinary tool call in a headers-only list.

#### Icon-only turns

A turn with work but no prose — aborted, or pure tool use — gets a bubble
containing only its icons.  It is styled (`.icons-only`, a faint dashed outline)
so that reads as deliberate rather than as a bubble that failed to render.

### 3. Pagination

#### 3.1 Why

Rendering 1,000+ messages through QWebEngine's `setHtml()` causes multi-second
pauses because the browser must load KaTeX (~900KB), highlight.js (~200KB), and
construct a massive DOM.  The Python-side HTML generation is fast (~17ms for
500 messages).  The bottleneck is entirely in the browser.

#### 3.2 Page boundaries

Pages cut **just before a user message**.  Tool calls, thinking blocks, and
assistant responses stay on the same page as their triggering user message.  A
page holds N user messages (configurable, default 10) plus everything that
follows each of them, so a turn is never split across pages.

#### 3.3 Visible window

Up to N pages are rendered at once (configurable, default 2), ending at the
**displayed end page**.  There is no scroll-triggered loading: the window moves
when the navigation controls are used, and while a turn is live the end page
follows the newest user message so the live turn is always rendered.  "Live"
is the turn boundary, not just open blocks — a running tool has no streaming
block (see §2).

A **steered message is a user turn like any other**: appending it to the DOM
instead of rebuilding is only safe while it stays on the page already being
shown.  If it opens a new page the window moves with it, or the new page is
never rendered and the transcript quietly stops advancing mid-turn.

#### 3.4 Page boundaries and controls

Two separate things, deliberately:

- A **bare dashed rule** (`.page-divider`) sits *in flow* between rendered page
  slices, marking a genuine boundary.  It carries no controls.
- The **navigation controls** float in a fixed bar outside the chat container:

```
◀ Prev    Pages 2–3 / 12    Next ▶    [Go]    ⤓ Bottom
```

Because the controls are out of the flow, drawing new bubbles cannot move them.
They were once emitted in flow three times — before the first page, between
pages, and after the last — which made them travel with the content and left a
stray bar at the top and bottom of the transcript.

Prev and Next use `visibility: hidden` when unavailable rather than being
omitted, so the bar does not jump as pages change.  `Go` jumps to a page number
on Enter.  `⤓ Bottom` returns to the newest message (see §12).

#### 3.5 Toggle state is ephemeral

Expand/collapse state for thinking blocks, tool stacks, and tool items is
**DOM-only**.  It is not stored in the data model.  When a page is re-rendered
(e.g. because a new user message triggers a new page), all toggles reset to
their default collapsed state.

### 4. Live streaming

Live blocks are addressed by **identity**, never by arrival order.  pi labels
every chunk with the message it belongs to and the content index within it, and
the renderer carries that label all the way through:

- `begin_block(msg_seq, index, kind, meta)` opens a block.  `kind` is one of
  `reply`, `thinking` or `tool`.
- `append_block_delta(msg_seq, index, kind, text)` appends to it.
- `end_block(msg_seq, index, kind, payload)` closes it, replacing whatever was
  buffered with the authoritative content the `*_end` event carries.
- `settle_message(msg_seq, message)` reconciles a whole message from
  `message_end`, which is what corrects an aborted or interleaved turn.

In the DOM the block is `<div id="blk-{msg_seq}-{index}">`, so placement comes
from the block's identity rather than from what happened to arrive before it.
The positional signals this replaced (assistant stream start/delta/end,
thinking started/delta/finished) inferred structure from adjacency, which is
what produced text filed into the wrong bubble.

`thinking` and `reply` are the kinds the renderer draws; `tool` is a documented
no-op here because tool rendering is keyed by `toolCallId` through
`upsert_tool_event`.  An unknown kind is reported to stderr rather than dropped.
That split is also why the live tail cannot be derived from open blocks alone —
see §2.

A live thinking block joins the agent-work bubble already in progress rather
than starting a row of its own.

At the end of each turn a **full `setHtml()` re-render** applies markdown,
syntax highlighting and KaTeX to the final content.

Errors and context overflow arrive through `message_end`'s `stopReason` and
`errorMessage`, not as a stream event.

### 5. Interactions

Most toggling is a plain inline `onclick` on the element, so no round trip to
Python is involved: `_toggleBucket` (the category icons), `_toggleAgentWork`,
`_toggleAwThinking`, `_toggleAwTool`.

Two actions do go back to Python over `thalamus://` URLs:

| Action | URL | Handler |
|--------|-----|---------|
| Copy a bubble | `thalamus://copy/{text}` | `_ChatPage.copyRequested` → clipboard |
| Go to a page | `thalamus://navigate-page/{n}` | `_ChatPage.navigatePageRequested` |

Both are handled in `_ChatPage.acceptNavigationRequest`, which returns `False`
so the navigation itself never happens.

Note: custom-scheme navigation is gated on a **user gesture** by Chromium.
Programmatic navigations — a synthetic `.click()`, or `location.href` set from
`runJavaScript` — are refused, so these paths cannot be exercised from an
automated harness.  They need a real click.

### 6. Code blocks

- Fenced code blocks (` ```lang\n...\n``` `) are rendered as `<pre>` elements
  with a dark background and monospace font.
- A **Copy button** appears in the top-right corner of each code block.
  Clicking copies the code text to the clipboard and shows "Copied!" feedback.
- **Syntax highlighting** is applied via highlight.js after page load.
- A `language-*` CSS class on the `<code>` element enables language-specific
  highlighting.
- JSON blocks are auto-formatted with `JSON.stringify(obj, null, 2)` for
  readability.

### 7. Math rendering

- LaTeX expressions are rendered by KaTeX (system-installed via Arch `katex`
  package).
- Markdown-level math delimiters are handled by mdit-py-plugins:
  `$...$` and `$$...$$` (dollarmath), `\(...\)` and `\[...\]` (texmath),
  `\begin{align}...\end{align}` (amsmath).
- KaTeX rendering runs in the browser via a `renderMathNodes()` JS function
  that finds `<eq>`, `<eqn>`, and `<div class="math amsmath">` elements.

### 8. Theme support

- CSS variables control all colors: `--bg`, `--text`, `--bubble-user`,
  `--bubble-assistant`, `--meta-text`, `--border`.
- A theme is a dict mapping variable names to hex color strings.
- Changing the theme triggers a full re-render.

### 9. Zoom

- The WebEngine view supports zoom via `Ctrl+scroll`.
- Zoom factor is clamped to 0.3–5.0 (QWebEngine limits).
- Zoom is persisted across application restarts.

### 10. Batch mode

During history loading, multiple `add_turn()` and `add_thinking()` calls may
accumulate before any render occurs.  A **batch mode** defers `setHtml()` until
all messages have been added, then renders once.

### 11. Render debouncing

Rapid successive calls to the render cycle are coalesced via a
`QTimer.singleShot(0)` — multiple updates within the same event loop iteration
result in a single `setHtml()` call.

### 12. Scroll behaviour

The bottom of the transcript is held by the **layout**, not by script.
`.chat-container` is a `column-reverse` flex container, so the first child
renders at the bottom and the bottom is `scrollTop 0`.  Content arriving
keeps a reader who is at the bottom there, and leaves a reader who has
scrolled away undisturbed — no flag, no observer, no scroll calls.

Consequences worth knowing:

- **`scrollTop` is negative away from the bottom.**  "At the bottom" is
  `scrollTop >= 0`.
- **The newest message is first in the DOM** so that it renders last on screen.
  `messages_to_html` reverses its rows and `_render` emits page slices in
  reverse.  Only the top-level rows reverse; what is inside a row keeps its
  order.  Visual order is unchanged: oldest at the top, newest at the bottom.
- **Live inserts prepend** (`insertAdjacentHTML('afterbegin')`); items inside a
  bubble still append.
- **Scroll anchoring is left at its default (on).**  It is what keeps the
  reader's view stable as content changes.  It was once disabled, back when the
  app maintained the position by hand and anchoring competed with it.

Two things still need code, and only two:

1. The page is rebuilt on every render and a rebuilt container starts at the
   bottom, so a reader part way up has their `scrollTop` kept in
   `sessionStorage` and restored on load.  The listener is on the **container** —
   an element's scroll events do not reach `window`.
2. The restore is offered again in a `requestAnimationFrame` before
   `data-ready` is set, because a restore clamps if the page has not laid out.
   Reading `scrollHeight` forces layout, so the target is scrollable-to by then.

The floating pagination bar carries a `⤓ Bottom` control for a reader who has
gone back up.  Staying at the bottom needs no control.

The page is hidden (`visibility: hidden`) while `data-ready="0"`, then revealed
in a `requestAnimationFrame` after DOM initialization completes.

### 13. Security

- **Tool args and results**: HTML-escaped before rendering in `<pre>` blocks
  and summary spans.  No raw user content appears unescaped.
- **Meta timestamps**: HTML-escaped.
- **Tool names**: HTML-escaped in headers and summaries.
- **User/assistant message content**: passed through a markdown renderer with
  `html: True` (standard CommonMark behavior).  Code block content is
  HTML-escaped.  The app is a local desktop tool rendering the user's own
  session transcripts — not untrusted external content.
- **Thinking text**: HTML-escaped.

### 14. Configuration

Two pagination settings, adjustable at runtime:

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Messages per page | 10 | 1–100 | Number of user messages per page |
| Pages displayed | 2 | 1–10 | Number of pages rendered at once |

Auto-collapse was removed.  Items collapse by default and the live tail stays
open (§2), which needs no thresholds.

Settings are persisted via QSettings so they survive application restarts.

### 15. Public API

The renderer exposes these operations to the main window:

**Data model:**
- `add_turn(role, text, meta)` — append a user or assistant speech bubble
- `add_thinking(text, msg_seq, index)` — append a *finished* thinking block
  (the history path)
- `add_activity(text, meta)` — a notice/status line
- `add_steer_message(text)` — insert a user turn during steering, no re-render
- `clear()` — reset all state

**Live streaming** (see §4):
- `begin_block(msg_seq, index, kind, meta)`
- `append_block_delta(msg_seq, index, kind, text)`
- `end_block(msg_seq, index, kind, payload)`
- `settle_message(msg_seq, message)`
- `upsert_tool_event(...)` — create or update a tool stack and its items

**Configuration:**
- `configure(page_size, pages_displayed)` — update pagination
- `set_show_thinking(bool)` / `set_show_tools(bool)`
- `set_theme(dict)` — set color theme
- `set_zoom(factor)` — or Ctrl+scroll
- `persist_zoom()` — save the zoom factor to QSettings

**Batch control:**
- `begin_batch()` — defer renders until `end_batch()`
- `end_batch()` — flush accumulated messages in one render

**Persistence:**
- `persist_zoom()` — save current zoom factor to QSettings

### 16. Empty state

An empty session (no messages) renders without error.  The chat container is
simply empty — no placeholder or welcome message is required.
