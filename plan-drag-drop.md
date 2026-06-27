# Plan: Drag-and-drop attachment sidebar

## Layout

A single `QFrame` containing both the text input and the attachment sidebar,
with a unified thinking-level border:

```
QFrame (border = thinking level color)
┌───────────────────────────────────────────┐
│ ┌─────────────────────┬─────────────────┐ │
│ │                     │ 📎 plan.md  ✕  │ │
│ │ QPlainTextEdit      │ 🖼️ diagram ✕  │ │
│ │ [stretch=1, greedy] │ 📄 data.csv ✕ │ │
│ │                     │                 │ │
│ │ [file: plan.md]     │ [scrollable    │ │
│ │ [image: diagram.png]│  QVBoxLayout   │ │
│ │                     │  in QScrollArea]│ │
│ └─────────────────────┴─────────────────┘ │
└───────────────────────────────────────────┘
```

## Behavior

### Drop handling
- `QPlainTextEdit.dragEnterEvent/dropEvent` override
- On drop of any file: insert `[file: basename]` at cursor position
- Add icon (file-type thumbnail or generic icon) + filename + ✕ to the sidebar column
- Emit signal to update UI state

### Clipboard paste (images only)
- Intercept Ctrl+V in ChatInput
- If clipboard contains image data: read, convert to base64 PNG
- Insert `[image: clipboard]` as text placeholder
- The image data is stored for sending via `images[]` RPC param
- No sidebar icon needed for pasted images (they're transient)

### Sidebar column (`QScrollArea` + `QVBoxLayout`)
- Built-in scrollbar when items overflow
- Default width: 0 (collapsed)
- When items exist: width auto-fits the widest item (~80px for 48px icon + padding)
- Each row: `QHBoxLayout` with `QLabel(icon)` + `QLabel(filename)` + `QPushButton("✕")`
- Click ✕: remove from sidebar + delete matching `[file: ...]` from text

### Text ↔ sidebar sync
- User can type/edit `[file: ...]` placeholders manually
- `textChanged` signal rescans text for `[...]` tokens and removes orphaned sidebar items
- Backspace over a `[file: ...]` token → sidebar syncs (item removed)
- Clicking ✕ sidebar button → removes the matching `[file: ...]` text

### Send
- Text is sent as-is (includes `[file: ...]` markers)
- If clipboard-pasted image exists, include via `images[]` param
- After send: clear text + sidebar + clipboard images

## Implementation order

1. Create attachment sidebar widget (`AttachmentSidebar`)
2. Create container `QFrame` with border and HBox layout
3. Override drop handling on ChatInput
4. Wire sidebar ↔ text sync (insert `[file: ...]` on drop, delete on ✕ click, rescans)
5. Wire into MainWindow (send includes attachments, indicator for non-image files)
