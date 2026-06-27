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

Command palette updated:
- Type hint: `QPlainTextEdit` → `QWidget`
- `installEventFilter` removed (keyboard events handled by JS bridge → `paletteAction` signal)
- `eventFilter` method removed
- `toPlainText()` → `self._input.text` (sync mirror property)
- `textCursor().hasSelection()` → removed
- Popup visibility communicated to JS via `set_popup_visible()`

**Key design:** The command palette stayed synchronous by using a Python-side text mirror (`InputPage._text`), updated by the JS `input` → `thalamus://text/...` bridge. No async restructuring needed.

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
- **Paste plain text**: no thumbnail, text goes into contentEditable (strip formatting)
- **Paste image from browser (HTML)**: strip the HTML, extract the raw image data
- **Drag non-image file**: show file-type icon in thumbnail column, store `file://` URL in metadata
- **Multiple attachments**: stack vertically in right column, scrollable
- **Delete attachment**: JS removes DOM element

### Styling
- Attachment column: width:0 by default, toggles to 80px via `.has-items` CSS class
- Thumbnails: 48×48px icons, rounded corners
- Placeholder: JS-toggled `.placeholder` class on `.input-text` (not `:empty`)
- Thinking border: Qt stylesheet on the QWebEngineView widget

### Edge cases
- **Focus loss**: focus can shift away from input (known issue, root cause not determined)
- **Very large images**: resize before base64 encoding (cap at ~10MB after encoding)
- **Error handling**: invalid image data, failed reads → toast/status message
- **Zoom**: QWebEngineView handles Ctrl+scroll natively per-view. Zoom levels persist separately via `"chat/zoom"` and `"input/zoom"` QSettings keys.
- **Theme switching**: JS sets `data-theme` attribute on body

---

## ⚠️ Gotchas discovered during implementation

### PySide6 `runJavaScript` cannot return objects
`QWebEnginePage.runJavaScript()` only supports primitive return types (string, number, boolean). Objects are silently converted to empty string. This broke the initial `getInputContent()` function which returned `{text, images}` — the Python callback always received `""`.

**Fix:** Return `JSON.stringify({text, images})` from JS and parse with `json.loads()` in Python.

### Chromium contentEditable caret can disappear when typing
The `:empty` CSS pseudo-class causes the caret to vanish when a contentEditable element transitions from empty to non-empty. The `:empty:before` placeholder technique triggers this bug.

**Workaround:** Use a JS-toggled `.placeholder` CSS class instead of `:empty`. However, even this may not fully resolve the issue in some Chromium builds. The caret can also disappear for other reasons — root cause still unclear.

### Focus shifts away from input box
Sometimes clicking Send or interacting elsewhere causes the input to lose focus, requiring an extra click to resume typing. Root cause not yet determined.

### Wheel events not propagated through Qt event system

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

## Step 1 implementation outcome (2026-06-27)

**Completed:**
- InputWebView (`src/ui/input_widget.py`) and input_page.py created
- MainWindow updated: ChatInput → InputWebView, send/follow-up/steer async
- Command palette updated: eventFilter removed, uses text mirror, notifies JS of popup
- ChatRenderer cleaned up: removed dead eventFilter, kept zoom persist

**Bugs found and fixed:**

| Bug | Cause | Fix |
|-----|-------|-----|
| Send does nothing | `runJavaScript` can't return objects → `getInputContent()` returned `{text,images}` but callback got `""` | Return `JSON.stringify()` from JS, `json.loads()` in Python |
| Caret disappears on typing | `:empty:before` placeholder triggers Chromium contentEditable bug | Replace with JS-toggled `.placeholder` class |
| Focus shifts away from input | Root cause unknown (possibly click → focus interaction with buttons) | Not yet fixed |
| Zoom independent, not preserved | Removed dead eventFilter; Chromium handles zoom internally | Each view persists independently (`"chat/zoom"`, `"input/zoom"`) |
| No caret at all (initial) | Missing `caret-color` CSS property | Added `caret-color: var(--text)` with universal selector |

**Known remaining issues:**
- Caret still sometimes disappears after typing in some Chromium builds
- Focus can shift away from the input box
