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
- The header shows "💭 Thinking" and a **[Show]/[Hide] toggle link**.
- **Collapsed by default** in history.  Expanded while streaming is active.
- During live streaming, the content div gets a **stable DOM ID** for JS delta
  insertion.
- Clicking the toggle manipulates the DOM directly — no full page reload.

#### 1.3 Tool stacks

A tool stack represents one tool execution (identified by `stack_id`, which is
the tool's `toolCallId`).  Some tools are multi-step (subagents) and produce
multiple items within one stack.  By far the common case is a single item.

- Rendered as centered **cards** with an orange-tinted background.
- **Card header** shows the tool icon + tool name of the first (non-node) item,
  plus a **[Show]/[Hide] toggle** for the whole stack.
- The **items container** is hidden by default.  Clicking Show reveals all items.
- Items are **hidden by default** when the stack is collapsed.

#### 1.4 Tool stack items — collapsed state

When collapsed, each item shows a **compact one-line header**:

```
bash | ls -la → total 48 | [Show] | complete
```

Components, left to right:
- **Title** — the tool name (bold).
- **Summary** — a human-readable preview of what the tool is operating on.
  Extracted from the structured `args` dict using per-tool field selectors
  (e.g. `bash→command`, `read→path`, `edit→path ← oldText`,
  `mempalace_search→query`, `subagent→task`).  Falls back to the formatted
  args/result if no structured args are available.  Truncated with CSS ellipsis.
- **Show/Hide toggle** — underlined link, toggles the item body.
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

#### 1.6 Pending approval state

When `status == "pending_approval"` and both `request_id` and `stack_id` are
present, the item shows action links:

- **Approve once** / **Deny once** — always shown.
- **Always allow** / **Always deny** — shown only if `tool_kind == "mcp"` and
  `mcp_server_id` is set.

The item is rendered expanded so the user can see the description and take
action immediately.

The pending item is also shown **above** the stack's items list in a distinct
yellow warning card so it's visible even when the stack is collapsed.

### 2. Agent work grouping

Consecutive `thinking` and `tool_stack` messages between turns are collected
into an **"Agent work (N)" collapsible bubble**:

- **Right-aligned** with a subdued "Agent work (N)" title showing the count
  of items inside.  The count is visible even when collapsed.
- A ▼/▶ indicator on the title toggles the group.  **Click to collapse or
  expand** the entire group.
- Auto-collapse keeps the most recent N groups expanded (configurable, default
  2).  Older groups collapse automatically on full re-render.
- **Three levels of nesting inside each group:**

  **Thinking blocks** — each gets its own light-blue sub-bubble with a
  "Thinking" label and ▼/▶ toggle.  Auto-collapse applies independently.

  **Tool entries** — each gets a light-green sub-bubble with a header showing
  the tool name and a one-line summary (e.g. "Bash: ls /tmp", "Read:
  /path/to/file", "Subagent: coder").  Click the header to expand/collapse
  the body (result output, status, errors).  Auto-collapse applies
  independently.

- All collapse state is **DOM-only** — toggles manipulate CSS classes via
  `runJavaScript()`.  Full re-renders reset to default collapsed state.
- The group is a rendering artifact — it does not exist in the data model.
  Non-turn messages are buffered during rendering and flushed as a group
  when a `turn` is encountered (or the page/message list ends).

### 3. Pagination

#### 3.1 Why

Rendering 1,000+ messages through QWebEngine's `setHtml()` causes multi-second
pauses because the browser must load KaTeX (~900KB), highlight.js (~200KB), and
construct a massive DOM.  The Python-side HTML generation is fast (~17ms for
500 messages).  The bottleneck is entirely in the browser.

#### 3.2 Page boundaries

Pages cut **just before a user message**.  Tool calls, thinking blocks, and
assistant responses stay on the same page as their triggering user message.
Agent work groups are never split across pages.

#### 3.6 Auto-collapse

Three independent auto-collapse settings control how many of the most recent
items stay expanded.  Items older than the count are rendered collapsed:

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Auto-collapse agent work | 2 | -1–20 | Collapse older agent-work bubbles; -1 or 0 collapses all |
| Auto-collapse thinking | 2 | -1–20 | Collapse older thinking blocks within agent-work bubbles |
| Auto-collapse tools | 2 | -1–20 | Collapse older tool entries within agent-work bubbles |

All three use the same threshold formula: `threshold = total if count <= 0
else max(0, total - count)`.  The header/summary remains visible even when
collapsed, with a triangular indicator (▼ expanded / ▶ collapsed).  Clicking
the header toggles individual items.

Counts are pre-computed in a first pass over the message slice so the
threshold is stable across all calls to the render function.

A page contains N user messages (configurable, default 10) plus all the thinking,
tools, and assistant responses that follow each user message.

#### 3.3 Visible window

Up to N pages are rendered simultaneously (configurable, default 2):
- The **anchor page** (most recent user message) is always rendered.
- The page before it is rendered above.
- The page after it (if it exists) is rendered below.
- A **sliding window**: when the user scrolls near the top of a rendered previous
  page, the page before that loads and the farthest page unloads.

#### 3.4 Page dividers

A dashed horizontal divider with navigation controls separates each page:
```
◀ Prev    Page 3 / 12    Next ▶    [Go]
```
- Shown at the **top** of the first rendered page.
- Shown **between** each rendered page.
- Shown at the **bottom** of the last rendered page.
- Prev dims/hides when on the first visible page.
- Next dims/hides when on the last page.
- The Go input jumps to an arbitrary page number on Enter.

#### 3.5 Toggle state is ephemeral

Expand/collapse state for thinking blocks, tool stacks, and tool items is
**DOM-only**.  It is not stored in the data model.  When a page is re-rendered
(e.g. because a new user message triggers a new page), all toggles reset to
their default collapsed state.

Toggle actions must **preserve scroll position** — after expanding or collapsing
an element, the page should not jump.

### 4. Live streaming

During live streaming, the renderer avoids full `setHtml()` calls and instead
patches the DOM via `runJavaScript()`:

- **Assistant text**: inserted into a stable `#assistant-stream-content` div.
  Deltas are appended as text nodes.
- **Thinking text**: inserted into a stable `#thinking-stream-content-N` div.
  Deltas are appended as text nodes.
- **Tool cards**: appended to the live agent work group's items container.
  A `_appendToolCard` JS function creates the card with the tool name and
  streaming summary.
- **Tool output**: a `_appendToolText` JS function updates the streaming output
  div as partial results arrive.
- **Tool finalization**: a `_finalizeToolCard` JS function replaces the streaming
  output with the final result, colored red for errors.
- **Agent work group**: automatically created and expanded during streaming via
  `_ensureAgentWorkGroup`.  Collapsed when the assistant starts speaking via
  `_closeAgentWorkGroup`.

At the end of each streaming turn, a **full `setHtml()` re-render** applies
markdown rendering, syntax highlighting, and KaTeX to the final assistant text.

Delta delivery is **debounced** — JS functions check if the user is scrolled
to the bottom before auto-scrolling.

### 5. Toggle interactions

All toggle actions are **DOM-only** via `runJavaScript()`:

| Toggle | URL pattern | JS behavior |
|--------|------------|-------------|
| Thinking expand/collapse | `thalamus://toggle-thinking/{index}` | Toggle `.thinking-content` display |
| Tool stack expand/collapse | `thalamus://toggle-tool-stack/{stack_id}` | Toggle `.tool-stack-items` display |
| Tool item expand/collapse | `thalamus://toggle-tool-item/{stack_id}/{item_key}` | Toggle `.tool-stack-item-body` display, update `data-expanded` attribute |
| Copy code | `thalamus://copy/{text}` | Copy text to system clipboard |
| Page navigation | `thalamus://navigate-page/{page_index}` | Jump to page |
| Tool approval | `thalamus://tool-approval/{action}/{stack_id}/{request_id}` | Approve/deny tool |

Toggle handlers must **preserve scroll position** by saving `window.scrollY`
before DOM changes and restoring it afterwards.

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

### 12. Scroll behavior

- After a full render, the page scrolls to the bottom by default.
- During live streaming, auto-scroll only happens if the user was already at
  the bottom (within an 8px tolerance).
- A `data-scroll` attribute on `<body>` controls the initial scroll position on
  page load.
- The page is hidden (`visibility: hidden`) while `data-ready="0"`, then
  revealed via `requestAnimationFrame` after DOM initialization completes.

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

Three pagination settings, adjustable at runtime:

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Messages per page | 10 | 1–100 | Number of user messages per page |
| Pages displayed | 2 | 1–10 | Number of pages rendered simultaneously |
| Auto-collapse agent work | 2 | -1–20 | Collapse older agent-work bubbles |
| Auto-collapse thinking | 2 | -1–20 | Collapse older thinking blocks |
| Auto-collapse tools | 2 | -1–20 | Collapse older tool entries |

Settings are persisted via QSettings so they survive application restarts.

### 15. Public API

The renderer exposes these operations to the main window:

**Data model:**
- `add_turn(role, text, meta)` — append a user or assistant speech bubble
- `add_thinking(text)` — append a thinking block (start live if `text=None`)
- `append_thinking_delta(text)` — append text to live thinking block
- `end_thinking()` — finalize live thinking, collapse the bubble
- `upsert_tool_event(stack_id, event_dict)` — create or update a tool stack and its items (handles `tool_call`, `tool_update`, `tool_result` event types)
- `begin_assistant_stream()` — create empty assistant bubble for live streaming
- `append_assistant_delta(text)` — append streaming text delta
- `end_assistant_stream()` — finalize assistant bubble, trigger full re-render
- `add_activity(text, meta)` — legacy system message
- `add_steer_message(text)` — insert user turn during steering (no re-render)
- `clear()` — reset all state

**Configuration:**
- `configure(page_size, pages_displayed, auto_expand_thinking)` — update pagination
- `set_theme(dict)` — set color theme
- `set_zoom(factor)` — adjust zoom (or use Ctrl+scroll)

**Batch control:**
- `begin_batch()` — defer renders until `end_batch()`
- `end_batch()` — flush accumulated messages in one render

**Persistence:**
- `persist_zoom()` — save current zoom factor to QSettings

### 16. Empty state

An empty session (no messages) renders without error.  The chat container is
simply empty — no placeholder or welcome message is required.
