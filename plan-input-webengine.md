# Plan: Switch input box to QWebEngineView

## Goal
Replace `ChatInput` (QPlainTextEdit) with a contentEditable QWebEngineView for the message input box, enabling rich content staging (pasted images, dragged files, display-vs-content separation) without inline icons in the text flow.

## Principles
- The input displays **text only** inline. Attachments (images, files) appear as a separate thumbnail strip below the input.
- The model receives clean structured data (`text` + `images[]`), never HTML.
- The command palette, keyboard shortcuts, thinking borders, and zoom continue working identically.

---

## Step 1 — Switch input to QWebEngineView

Replace `ChatInput` (QPlainTextEdit) with a new `InputWebView` (QWebEngineView-based).

### 1a. Create the input HTML template

A minimal contentEditable page at `src/ui/input_page.py`:

```
<body contenteditable="true" data-placeholder="Type a message…">
```

CSS:
- Match the theme (dark/light background, text color)
- Thinking-level border via CSS class on body
- Placeholder via `:empty:before` pseudo-element
- Same monospace font as current input

JS:
- `input` event → `thalamus://text-changed/<encoded>` bridge
- Key handlers for Enter (→ send), Tab (→ command palette), Up/Down/Escape (→ popup nav) when applicable
- `getInputContent()` — serializes to `{text: string, images: [{data, mimeType}]}`
- Ctrl+scroll → bridge zoom to Python

### 1b. Create InputWebView widget

New file `src/ui/input_widget.py`:

- `InputWebView(QWebEngineView)` — thin wrapper
- `InputPage(QWebEnginePage)` — intercepts `thalamus://` URLs, emits Qt signals
- Signals: `sendRequested`, `textChanged(str)`, `popupAction(str)` (tab/up/down/enter/escape)

### 1c. Wire into MainWindow

Replace `ChatInput` usage in `main_window.py`:

| Current (QPlainTextEdit) | New (InputWebView) |
|---|---|
| `chat_input.sendRequested` | `input_view.sendRequested` |
| `chat_input.textChanged` | `input_view.textChanged` (bridge from JS `input` event) |
| `chat_input.toPlainText()` | `input_view.get_text(callback)` (async via `runJavaScript`) |
| `chat_input.clear()` | `input_view.clear()` (JS `body.innerHTML = ''`) |
| `chat_input.setFocus()` | `input_view.setFocus()` (same — QWidget method) |
| `set_thinking_border_color()` | JS: `body.dataset.thinking = level` → CSS handles |

### 1d. Update command palette

Command palette currently expects `QPlainTextEdit` typed methods. Update the type hint and wire:

| Current | New |
|---|---|
| `_input.textChanged.connect(...)` | `input_view.textChanged.connect(...)` (same signal, different source) |
| `_input.toPlainText()` in eventFilter | `_input.get_text()` via async callback |
| `_input.installEventFilter(self)` | Same — QWebEngineView is a QWidget, eventFilter still works |
| `_input.textCursor().hasSelection()` | JS: `window.getSelection().toString()` via bridge |

**Key change:** Command palette's `toPlainText()` calls become async. Affects `_on_text_changed`, `_show`, `_dispatch`, and the eventFilter's Enter handler. Each uses a callback chain.

---

## Step 2 — Implement drag-and-drop

### 2a. Attachment column (inside the WebEngine)

The attachment column lives inside the web view's HTML, alongside the contentEditable:

```
QWebEngineView (border = thinking level color)
┌──────────────────────────────────────────────────┐
│ ┌────────────────────┐ ┌───────────────────────┐ │
│ │ contentEditable    │ │ 📎 attachment icons   │ │
│ │ (text only, grows) │ │ (scrollable column,   │ │
│ │                    │ │  width:0 when empty)  │ │
│ └────────────────────┘ └───────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- **Default width: 0** — hidden, doesn't affect layout
- When attachments exist: width toggles to ~80px via CSS class
- **Overflow-y: auto** — scrollbar appears when items exceed height
- Each entry: thumbnail icon, filename tooltip, ✕ delete button
- Delete button: JS removes the DOM element + Python removes from data via bridge
- Click thumbnail → popup dialog (`QDialog`) with full preview + Save button

### 2b. Drop handling (JS side)

In the input page JS:
- `dragover` → prevent default (allow drop)
- `drop` → `event.dataTransfer.files` → `FileReader.readAsDataURL()` → emit `thalamus://file-dropped/{name}/{mime}/{base64}`
- Don't insert into contentEditable — just bridge the data to Python

### 2c. Python side

- Bridge receives base64 data → creates thumbnail widget in the strip
- Stores in `_attachments: list[dict]` — `{data, mimeType, name}`
- On Send: serializes attachments into `submit_message(text, images=[...])`

### 2d. Paste handling

Similar flow but from clipboard:
- JS `paste` event → `clipboardData.items` → detect `image/png` → `canvas.toDataURL()` → bridge → thumbnail

---

## Step 3 — Fine-tune / edge cases

### Behavior
- **Empty input + Enter**: no-op (same as today)
- **Paste plain text**: no thumbnail, text goes into contentEditable
- **Paste image from browser (HTML)**: strip the HTML, extract the raw image data
- **Drag non-image file**: show file-type icon in thumbnail strip, store `file://` URL in metadata
- **Multiple attachments**: sort thumbnails horizontally, scrollable if overflow
- **Delete attachment**: remove from strip + `_attachments` list

### Styling
- Column: zero-width by default, smooth transition on expand (`QPropertyAnimation` or just `setFixedWidth`)
- Thumbnails: 48×48px icons, rounded corners, consistent with theme
- Placeholder: hidden when any content (text or attachments) exists
- Thinking border: still changes input border color (on the web view, not the attachment column)

### Edge cases
- **Input focus loss**: keep focus in contentEditable after thumbnail interaction
- **Very large images**: resize before base64 encoding (cap at ~10MB after encoding)
- **Error handling**: invalid image data, failed reads → toast/status message
- **Zoom**: QWebEngineView handles Ctrl+scroll natively via Chromium's internal zoom. No Python-side zoom sync — each view zooms independently. This matches Chromium's default behavior and avoids fighting the renderer process.
- **Theme switching**: re-render input page with new CSS

---

## ⚠️ Learned: QWebEngineView input events

A key discovery during implementation:

**Qt event filters do NOT receive wheel events from QWebEngineView.**
Chromium's compositor thread handles input (scroll, wheel) directly in the renderer process, bypassing the Qt main-thread event system entirely.

`wheelEvent` virtual method overrides *do* receive events when sent via `QApplication.sendEvent()`, but **not for real user input** — real wheel events go straight to the Chromium compositor.

This means:
- {" ": " "}

**Implications:**
- Ctrl+scroll zoom on the input and chat views happens via Chromium's native mechanism — each view independently. This is fine and expected behavior.
- The old ChatInput (QPlainTextEdit) had working Ctrl+scroll zoom because `QPlainTextEdit` is a standard Qt widget that processes wheel events through the Qt event system.
- If we ever need to intercept wheel events on a QWebEngineView (e.g., for custom zoom sync), we must use **JavaScript** in the page (`document.addEventListener('wheel', ...)`) and bridge back to Python.

---

## What stays the same

- The chat renderer — no changes
- PiRPCBridge — no changes
- `submit_message(text, images)` API — unchanged
- Send/abort/steer/follow-up flow — same logic, just async text extraction
- Keyboard shortcuts (Ctrl+L, Ctrl+P, Shift+Tab, etc.) — wired in MainWindow, unaffected

---

## Open question

Can the command palette's async conversion be deferred? Instead of making every `toPlainText()` call async, we could keep a Python-side mirror of the input text (updated via the JS `input` → bridge → `textChanged` signal), and read from that mirror synchronously. This avoids restructuring the command palette's synchronous code paths.
