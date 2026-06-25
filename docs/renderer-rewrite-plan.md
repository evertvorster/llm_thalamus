# Chat Renderer Clean-Room Rewrite Plan

## Background

The current `src/ui/chat_renderer.py` (2,291 lines) is a monolithic mess. We're replacing it with a clean, maintainable implementation through a clean-room rewrite — starting fresh with no baggage from the old code, guided by the design spec at `chat-renderer-redesign.md`, the pagination design at `paginated-renderer.md`, and the performance analysis at `renderer-performance-analysis.md`.

## Data Inputs — Two Sources

The renderer receives data from exactly two sources. Understanding these contracts is essential.

### Source A: Live RPC events (streaming)

Pi sends events via `pi --mode rpc` stdout. The `PiRPCBridge` routes them to Qt signals:

| Signal | Signature | When | What to do |
|--------|-----------|------|------------|
| `assistant_stream_start` | `Signal()` | New assistant message begins | `begin_assistant_stream()` |
| `assistant_stream_delta` | `Signal(str)` | Text chunk | `append_assistant_delta(text)` |
| `assistant_stream_end` | `Signal()` | Assistant message complete | `end_assistant_stream()` |
| `thinking_started` | `Signal()` | Thinking block begins | `add_thinking()` |
| `thinking_delta` | `Signal(str)` | Thinking text chunk | `append_thinking_delta(text)` |
| `thinking_finished` | `Signal()` | Thinking block ends | `end_thinking()` |
| `tool_execution_start` | `Signal(str, str, dict)` | (callId, name, args) | `upsert_tool_event(callId, {"event_type":"tool_call", ...})` |
| `tool_execution_update` | `Signal(str, str)` | (callId, partialText) | `upsert_tool_event(callId, {"event_type":"tool_update", ...})` |
| `tool_execution_end` | `Signal(str, str, str, bool, obj)` | (callId, name, result, isError, details) | `upsert_tool_event(callId, {"event_type":"tool_result", ...})` |
| `history_turn` | `Signal(str, str, str)` | (role, text, timestamp) from `get_messages` | `add_turn(display_role, text)` in batch |
| `history_thinking` | `Signal(str, str)` | (thinkingText, timestamp) from `get_messages` | `add_thinking(text)` in batch |

MainWindow currently maps:
- `history_turn("user", ...)` → `add_turn("human", text)`
- `history_turn("assistant", ...)` → `add_turn("you", text)`
- `tool_execution_start(callId, name, args)` → `upsert_tool_event(callId, {"event_type":"tool_call", "tool_call_id": callId, "tool_name": name, "args": args})`
- `tool_execution_end(callId, name, result, isError, details)` → `upsert_tool_event(callId, {"event_type":"tool_result", "tool_call_id": callId, "tool_name": name, "result": result, "ok": not isError, "details": details})`

### Source B: Session files (history loading)

Session files are JSONL at `~/.pi/agent/sessions/*.jsonl`. Each line has `"type":"message"` with an `AgentMessage`:

```json
// User message
{"type":"message","message":{"role":"user","content":[{"type":"text","text":"..."}],"timestamp":123}}

// Assistant message (may contain thinking + text + toolCalls)
{"type":"message","message":{"role":"assistant","content":[
    {"type":"thinking","thinking":"reasoning..."},
    {"type":"text","text":"response..."},
    {"type":"toolCall","id":"call_xxx","name":"bash","arguments":{"command":"ls"}}
],"timestamp":123}}

// Tool result
{"type":"message","message":{"role":"toolResult","toolCallId":"call_xxx","toolName":"bash",
    "content":[{"type":"text","text":"output..."}],"isError":false,"timestamp":123}}
```

The `PiRPCBridge._emit_structured_history()` method processes these into signals:
1. Indexes all `toolResult` messages by `toolCallId`
2. For each `assistant` message: emits `tool_execution_start`/`tool_execution_end` for each `toolCall` block (matched with result), emits `history_thinking` for `thinking` blocks, emits `history_turn` for `text` blocks
3. For each `user` message: emits `history_turn("user", text, ts)`
4. Skips `toolResult` and `bashExecution` as separate bubbles (already handled via tool signals)

## Internal Data Model

The renderer stores messages in `_messages: list[dict]`. Each dict has a `kind` field:

```python
# A user or assistant turn
{"kind": "turn", "role": "human"|"you"|"system", "content": "markdown text", "meta": "optional timestamp"}

# A thinking block (collapsible reasoning)
{"kind": "thinking", "text": "thinking text", "expanded": False}

# A tool execution stack (1 stack per tool call, contains items)
{"kind": "tool_stack", "stack_id": "call_xxx", "items": [...], "expanded": False}

# Activity message (legacy, keep for compatibility)
{"kind": "activity", "text": "...", "meta": "..."}
```

Tool stack items have:
```python
{
    "tool_name": "bash",
    "tool_call_id": "call_xxx",
    "status": "running"|"ok"|"error"|"denied"|"pending_approval",
    "args": {"command": "ls"},        # raw args dict
    "_fmt_args": "<pre>...</pre>",    # HTML-escaped formatted args
    "_fmt_result": "<pre>...</pre>",  # HTML-escaped formatted result
    "_fmt_stream": "...",             # HTML-escaped streaming partial text
    "_fmt_details": "...",            # formatted subagent details (optional)
    "result": "...",                  # raw result
    "error": "...",                   # error message (optional)
    "tool_kind": None|"mcp",         # optional
    "mcp_server_id": None|"...",     # optional
    "step": None|int,                # optional
    "item_kind": None|"node",        # optional
    "request_id": None|"...",        # for pending_approval
    "description": None|"...",       # for pending_approval
}
```

## Required Features (from the redesign spec)

### Core rendering
1. **`messages_to_html()`** — pure function, no Qt imports. Renders a slice of `_messages` to inner HTML.
2. **`_build_html_document()`** — wraps inner HTML in the full page template with theme variables.
3. **Message kinds**: `turn` (human/you), `thinking` (collapsible), `tool_stack` (collapsible with items), `activity`
4. **Agent work groups**: auto-group consecutive thinking + tool_stack items into a collapsible group wrapper
5. **Markdown rendering**: `format_content_to_html()` using markdown-it with dollarmath/texmath/amsmath plugins
6. **KaTeX/LaTeX rendering**: via JS `renderMathNodes()` function, called after DOM load
7. **Code blocks**: syntax highlighting via highlight.js, copy buttons via JS `enhanceCodeBlocks()`
8. **Status badges**: colored pills for tool item status (running/ok/error/denied/pending)
9. **Approval UI**: for `pending_approval` items, show Approve/Deny/Always allow/Always deny links

### Pagination
10. **Page slicing**: divide `_messages` at user message boundaries, configurable page size (default 10 user msgs)
11. **Configurable window**: render N pages at once (default 2: current + previous)
12. **Page dividers**: dashed `<hr>` with page numbers and Prev/Next nav buttons (top and bottom)
13. **Sliding window**: when user scrolls to top of previous page, load the page before it and drop the farthest one
14. **Ephemeral toggles**: toggle state is DOM-only, resets on re-render

### Streaming
15. **Live assistant streaming**: JS `_beginAssistantBubble()` / `_appendAssistantDelta()` / `_finalizeAssistantBubble()`
16. **Live tool streaming**: JS `_appendToolCard()` / `_appendToolText()` / `_finalizeToolCard()`
17. **Live thinking streaming**: JS for thinking block insertion during streaming
18. **Agent work group during streaming**: auto-create and expand group for live tool/thinking items
19. **Scroll position preservation**: JS `_saveScrollY()` / `_restoreScrollY()` for toggle actions

### Configuration
20. **`configure(page_size, pages_displayed, auto_expand_thinking)`** — memory-only, no QSettings
21. **`set_zoom(factor)`** — just calls `setZoomFactor()` on the web view
22. **`set_theme(theme_dict)`** — stores theme, triggers re-render

### Batch mode
23. **`begin_batch()` / `end_batch()`** — defer `_render()` until batch ends (for history loading)
24. **`_request_render()`** — QTimer coalescing to debounce rapid calls

### Data model
25. **`add_turn(role, text, meta)`** — append a turn message
26. **`add_thinking(text)`** — append a thinking block
27. **`append_thinking_delta(text)`** — append to current thinking block (streaming)
28. **`end_thinking()`** — finalize current thinking block
29. **`upsert_tool_event(stack_id, event_dict)`** — create/update tool stacks and items (3 event types)
30. **`begin_assistant_stream()`** — prepare new assistant bubble
31. **`append_assistant_delta(text)`** — append streaming text
32. **`end_assistant_stream()`** — finalize assistant bubble
33. **`add_activity(text, meta)`** — legacy activity message
34. **`add_steer_message(text)`** — steer/interrupt message
35. **`clear()`** — reset all state

### URL bridge
36. **`_ChatPage(QWebEnginePage)`** — intercepts `thalamus://` URLs for toggles, copy, navigation, approval
37. **URL handlers**: toggle-thinking, toggle-tool-stack, toggle-tool-item, copy, navigate-page, tool-approval/*
38. **All `thalamus://` URLs return `False`** from `acceptNavigationRequest` (prevents navigation)
39. **`createWindow()` returns `self`** — prevents popup windows

### JS toggle handlers (DOM-only, no re-render)
40. **`_on_thinking_toggle(index)`** — JS toggle of thinking content visibility
41. **`_on_tool_stack_toggle_requested(stack_id)`** — JS toggle of tool stack items visibility
42. **`_on_tool_stack_item_toggle_requested(stack_id, item_key)`** — JS toggle of individual item body
43. **Scroll position preservation in all toggle handlers**

### What moves to main_window.py
44. **QSettings**: page_size, pages_displayed, auto_expand_thinking — read on startup, call `chat.configure()`
45. **Zoom persistence**: MainWindow reads/writes QSettings, calls `chat.set_zoom()` on Ctrl+scroll
46. **No QSettings inside ChatRenderer** at all — the renderer is a pure view

## Implementation Order

### Phase 1: Write `messages_to_html()` and module-level helpers

**File:** `src/ui/chat_renderer_v2.py`

Pure function layer — no Qt imports, no classes, no side effects. Can be tested in isolation.

1. Copy over these **existing helpers as-is** (they work correctly):
   - `format_content_to_html()` — markdown → HTML with LaTeX
   - `_format_json_block()` — format Python value for `<pre>` display
   - `_tool_item_status_label()` — status → (label, CSS class)
   - `_tool_item_title()` — item → display name
   - `_tool_icon()` — tool name → emoji icon
   - `_fmt_tokens()` — count → k/M suffix
   - `_format_subagent_details()` — details dict → compact HTML
   - `_item_summary()` — extract one-line preview
   - `_md` parser setup (markdown-it with plugins)
   - `HTML_TEMPLATE` string (trimmed — remove dead CSS)

2. **Watch out — `re` module**: the current code uses `import re as _re` inside `_render_tool_stack_item`. In the new code, `import re` goes at the top of the file.

3. Write these **pure render functions**:
   - `messages_to_html(messages, assistant_stream_index, thinking_stream_index, page_start, page_end) → str`
   - `_build_html_document(inner_html, theme, scroll_to_bottom) → str`
   - `_render_thinking_block(msg, idx, thinking_stream_index) → str`
   - `_render_tool_stack_card(msg, stack_id) → str`
   - `_render_tool_stack_item(item, stack_id) → str`
   - `_render_turn(msg, is_assistant_streaming, is_latest) → str`
   - `_render_agent_work_group(items, expanded) → str`
   - `_page_nav_html(first_page, last_page, total_pages) → str`

4. **Agent work group logic**: consecutive thinking/tool_stack messages get wrapped in `<div class="agent-work-group">`. Last group is expanded if streaming is active. One nesting level only.

5. **CSS string**:
   - Reuse the existing CSS with fixes from `tool-call-rendering-fix.md`
   - `.tool-stack-item-toggle` must be VISIBLE (not `display: none`)
   - `.tool-stack-item[data-expanded="true"] .tool-stack-item-summary { display: none; }`
   - `.tool-stack-item[data-expanded="false"] .tool-stack-item-summary { display: inline; }`
   - Keep page divider CSS, status badges, copy buttons, etc.

### Phase 2: Write `_build_html_document()` and JavaScript

6. **HTML template**: Same structure as current:
   ```html
   <!DOCTYPE html><html><head><style>...</style><script>...</script></head>
   <body data-ready="0"><div class="chat-container">{messages_html}</div>
   <script>/* init */</script></body></html>
   ```

7. **JavaScript runtime** (inline in template, ~150 lines):
   - `_ensureAgentWorkGroup()` / `_updateWorkGroupCount(n)` — live streaming group management
   - `_appendToolCard(id, name, summary)` — live tool card insertion
   - `_appendToolText(id, text)` — streaming tool output
   - `_finalizeToolCard(id, resultHtml, isError)` — finalize tool card
   - `_closeAgentWorkGroup()` — collapse when assistant starts speaking
   - `_beginAssistantBubble()` — insert assistant bubble during streaming
   - `_appendAssistantDelta(text)` — append text to streaming bubble
   - `_isAtBottom(margin)` / `_scrollToBottom()` — scroll helpers
   - `_saveScrollY()` / `_restoreScrollY(y)` — scroll preservation for toggles
   - `_appendUserBubble(text)` — user message insertion (non-paginated streaming)
   - `_toolIcon(name)` — emoji lookup
   - `_htmlEscape(s)` — HTML escape utility
   - `enhanceCodeBlocks()` — copy buttons on code blocks
   - `renderMathNodes()` — KaTeX rendering
   - `_handleGoToPage(inputEl, total)` — page navigation
   - Scroll event handler for sliding page window
   - `onpageshow` / `onload` — DOM init

   **Important**: The `_appendToolCard` JS function already exists and should be copied as-is but verified. The toggle JS must set `data-expanded` attribute on the item element (as documented in `tool-call-rendering-fix.md`).

### Phase 3: Write `ChatRenderer` class

8. **Class skeleton**:
   ```python
   class ChatRenderer(QWidget):
       _SETTINGS_KEY = "llm-thalamus"
       _SETTINGS_ORG = "llm-thalamus"

       toolStackToggleRequested = Signal(str)         # stack_id
       toolStackItemToggleRequested = Signal(str, str) # stack_id, item_key
       thinkingToggleRequested = Signal(int)            # index
       copyRequested = Signal(str)                      # text
       navigatePageRequested = Signal(int)              # page index
   ```

9. **`__init__()`**:
   - Create `QWebEngineView`
   - Create `_ChatPage` instance
   - Read settings from QSettings for initial values (BUT document that these are just initial inputs — no re-reading or persistence)
   - Set up `_messages: list[dict] = []`
   - Streaming state: `_assistant_stream_active`, `_assistant_stream_index`, `_thinking_stream_index`
   - Pagination state: `_page_size`, `_pages_displayed`, `_display_end_page`, `_auto_expand_thinking`
   - Batch state: `_batch_mode`, `_render_pending`

10. **Pagination helpers**:
    - `_user_message_indices() → list[int]`
    - `_current_page_index() → int`
    - `_total_pages() → int`
    - `_page_message_range(page_index) → tuple|None`
    - `_visible_page_indices() → list[int]`

11. **Tool management**:
    - `_find_tool_stack(stack_id) → dict|None`
    - `_ensure_tool_stack(stack_id) → dict`
    - `_ensure_tool_stack_item(stack, tool_call_id, request_id, event_type, event) → dict`
      - Lookup order: by `request_id`, then by `tool_call_id`, then create new

12. **`upsert_tool_event()`** — handles three event types:
    - `"tool_call"`: create/update item, set `_fmt_args`, emit JS `_appendToolCard`
    - `"tool_update"`: update `_partial_text`/`_fmt_stream`, emit JS `_appendToolText`
    - `"tool_result"`: set result/status, update `_fmt_result`, clear streaming state, emit JS `_finalizeToolCard`

13. **`configure()`**, **`set_zoom()`**, **`set_theme()`** — memory-only setters

14. **`begin_batch()` / `end_batch()`** — batch render deferral

15. **Render cycle**:
    - `_request_render()` — QTimer coalescing
    - `_do_deferred_render()` — clear pending flag, call `_render()`
    - `_render()`:
      1. Return if in batch mode
      2. Determine visible page range
      3. Call `messages_to_html()` for each page
      4. Build page navigation dividers
      5. Wrap in `_build_html_document()`
      6. Call `self._view.setHtml(html, QUrl("file:///"))`

16. **`add_turn()`** — append message, detect page boundary crossing, trigger render
17. **`add_thinking()` / `append_thinking_delta()` / `end_thinking()`** — thinking lifecycle
18. **`begin_assistant_stream()` / `append_assistant_delta()` / `end_assistant_stream()`** — streaming lifecycle
19. **`add_activity()` / `add_steer_message()`** — legacy methods
20. **`_exec_js(js)`** — convenience wrapper for `page().runJavaScript(js)`

### Phase 4: Write `_ChatPage` class

21. Subclass `QWebEnginePage` with `acceptNavigationRequest()` handler for `thalamus://` URLs:
    - `thalamus://toggle-tool-stack/{stack_id}` → emit `toolStackToggleRequested`
    - `thalamus://toggle-tool-item/{stack_id}/{item_key}` → emit `toolStackItemToggleRequested`
    - `thalamus://toggle-thinking/{index}` → emit `thinkingToggleRequested`
    - `thalamus://copy/{text}` → emit `copyRequested`
    - `thalamus://navigate-page/{page_index}` → emit `navigatePageRequested`
    - `thalamus://tool-approval/{action}/{stack_id}/{request_id}` → emit via bridge
    - All return `False`

22. **`createWindow()` returns `self`** — prevents new windows from tooltips/hovercards

### Phase 5: Wire into `main_window.py`

23. **New signal connections**:
    - `bridge.tool_execution_start` → `chat.upsert_tool_event()`  (already wired)
    - `bridge.tool_execution_update` → `chat.upsert_tool_event()` (already wired)
    - `bridge.tool_execution_end` → `chat.upsert_tool_event()`   (already wired)
    - `bridge.thinking_started` → `chat.add_thinking()` (CHANGE: currently does nothing)
    - `bridge.thinking_delta` → `chat.append_thinking_delta()` (CHANGE: currently does nothing)
    - `bridge.thinking_finished` → `chat.end_thinking()` (CHANGE: currently does nothing)
    - `bridge.history_turn` → `chat.add_turn()` (already wired)
    - `bridge.history_thinking` → `chat.add_thinking()` (already wired)

24. **Move QSettings to MainWindow**:
    - Read `renderer/page_size`, `renderer/pages_displayed`, `renderer/auto_expand_thinking` on startup
    - Call `chat.configure(page_size, pages_displayed, auto_expand_thinking)`
    - On change (from Configure dialog), write settings then call `chat.configure()`
    - Zoom: handle Ctrl+scroll in MainWindow, persist via QSettings, call `chat.set_zoom()`

25. **Connect `_ChatPage` signals**:
    - `chat.thinkingToggleRequested.connect(self.chat._on_thinking_toggle)`
    - `chat.toolStackToggleRequested.connect(self.chat._on_tool_stack_toggle_requested)`
    - `chat.toolStackItemToggleRequested.connect(self.chat._on_tool_stack_item_toggle_requested)`
    - `chat.navigatePageRequested.connect(...)` — scroll to page
    - `chat.copyRequested.connect(...)` — copy to clipboard

### Phase 6: Delete old file

26. Only after the new implementation passes the comparison test:
    - Empty session
    - Simple user/assistant conversation
    - Session with thinking blocks
    - Session with tool calls (all statuses)
    - Session with subagent dispatch
    - Streaming session
    - Session switch
    - Zoom applied

27. Rename `chat_renderer_v2.py` → `chat_renderer.py`
28. Remove old `chat_renderer.py`

## Data Structures Summary

The rewrite reads `_messages[]` in exactly one place: `messages_to_html()` and its render helpers. Every other method writes to `_messages[]` or manages render state. This makes the data flow easy to reason about:

```
add_turn() / add_thinking() / upsert_tool_event() / etc.
        │
        ▼
    _messages[]  ← authoritative data model
        │
        ▼
    _render() → messages_to_html() → _build_html_document() → setHtml()
```

Toggles bypass the data model entirely:
```
User clicks toggle link
        │
        ▼
    _ChatPage.acceptNavigationRequest()
        │
        ▼
    Signal → _on_*_toggle() → _exec_js("DOM manipulation")
```

## Critical Implementation Notes

1. **No QSettings in ChatRenderer** — the renderer takes configuration via `configure()` and `set_zoom()`. MainWindow owns persistence.

2. **No `render_chat_html()` wrapper** — external callers use `messages_to_html()` + `_build_html_document()` directly.

3. **No `body_html_cache`** — small pages make caching unnecessary. Full re-render of 1-2 pages is fast (Python side ~2ms).

4. **`_fmt_args` and `_fmt_result` are already HTML-escaped** — don't double-escape. The `_item_summary()` helper strips HTML tags with regex for the preview.

5. **Agent work groups**: one nesting level only. The group wraps items. Individual items keep their own collapse state.

6. **All `thalamus://` URLs return `False`** from `acceptNavigationRequest`.

7. **Scroll position preservation**: critical for UX — JS toggle handlers must save/restore scroll position.

8. **CSS toggle rules**: `.tool-stack-item-toggle` must be visible. Summary hidden when `data-expanded="true"`, shown when `"false"`.

9. **Re-entrant `_render()`**: must handle being called during a `setHtml()` load cycle without crashing.

10. **`_exec_js()` calls during streaming** happen immediately (no render needed) — the JS functions handle DOM insertion directly.
