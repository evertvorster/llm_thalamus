# Tool Call Rendering Fix

**Status:** Plan — awaiting implementation approval  
**Created:** 2026-06-25  
**Related code:** `src/ui/chat_renderer.py`  
**Obsidian vault:** `Projects/Programming/llm-thalamus/`

---

## Problem

Tool calls in the message history don't show the command/args summary while collapsed, and when expanded they show the command args but not the full tool output. The root cause is that the **per-item toggle link is hidden by CSS**, preventing users from expanding individual tool items to see the full Arguments/Output sections.

## Root Cause

Three bugs in `src/ui/chat_renderer.py`:

| # | Location | Issue |
|---|----------|-------|
| 1 | CSS line 168 | `.tool-stack-item-toggle { display: none }` — per-item "Show"/"Hide" link is invisible |
| 2 | CSS ~line 176 | `.tool-stack-item-summary` has no toggle rules — the comment says "hidden by default, shown when collapsed" but there's no CSS to actually do this |
| 3 | JS line ~698 | `_appendToolCard()` during live streaming creates a simple card without args summary — only the tool name shows |

The **toggle handler infrastructure already works** (`_on_tool_stack_item_toggle_requested` in Python + `_appendToolCard` JS). The URL scheme handler for `thalamus://toggle-tool-item/` is wired. Just the CSS hides the clickable link.

## Changes

### Phase 1 — Unhide and style the per-item toggle (CSS)

**File:** `src/ui/chat_renderer.py`, CSS section

**1a.** Remove `display: none` from `.tool-stack-item-toggle`. Replace with a visible style:

```css
.tool-stack-item-toggle {
    font-size: 12px;
    color: var(--meta-text);
    text-decoration: underline;
    cursor: pointer;
    flex: 0 0 auto;
    white-space: nowrap;
}
```

**1b.** Add CSS rules to toggle the summary visibility based on item body state:

```css
/* Summary visible when body is collapsed, hidden when expanded */
.tool-stack-item[data-expanded="true"] .tool-stack-item-summary {
    display: none;
}
.tool-stack-item[data-expanded="false"] .tool-stack-item-summary {
    display: inline;
}
```

The `data-expanded` attribute is set by the JS toggle handler (`_on_tool_stack_item_toggle_requested`) — currently it toggles `bodyDiv.style.display`. We'll also set the `data-expanded` attribute on the item element at the same time, so the CSS rule works.

### Phase 2 — Update `_render_tool_stack_item` to emit `data-expanded` (Python)

**File:** `src/ui/chat_renderer.py`, `_render_tool_stack_item()`

The item div currently has `data-item-key` but not `data-expanded`. Add it:

```python
item_expanded = 'true' if expanded else 'false'
return (
    f'<div class="tool-stack-item" data-item-key="{escape(item_key)}" data-expanded="{item_expanded}">'
    ...
)
```

Also update `_on_tool_stack_item_toggle_requested` to set `data-expanded` on the item element when toggling:

```javascript
children[i].setAttribute('data-expanded', wasHidden ? 'false' : 'true');
```

This replaces the CSS-only approach — JS sets the attribute, CSS responds.

### Phase 3 — Update toggle JS to manage `data-expanded` (JS)

**File:** `src/ui/chat_renderer.py`, `_on_tool_stack_item_toggle_requested()`

Current JS toggles `bodyDiv.style.display` between `''` and `'none'`. Add the `data-expanded` attribute toggle on the parent item element:

```javascript
// After toggling bodyDiv style:
children[i].setAttribute('data-expanded', wasHidden ? 'false' : 'true');
```

Also update the toggle link text from "Show"/"Hide" to match (currently the link is hidden, so this is cosmetic but good practice):

```javascript
// Update toggle link text — already present for thinking toggle:
var toggle = children[i].querySelector('.tool-stack-item-toggle');
if (toggle) toggle.textContent = wasHidden ? 'Show' : 'Hide';
```

### Phase 4 — Update `_appendToolCard` JS for live streaming (optional)

**File:** `src/ui/chat_renderer.py`, JS `_appendToolCard()`

The live streaming JS card currently shows only the tool name. Add a second parameter for the args summary, passed from the Python side.

**Python side** — in `upsert_tool_event`, `event_type == "tool_call"`:
```python
args_summary = _tool_args_summary(item)
self._exec_js(
    "_appendToolCard(" + json.dumps(stack_id) + "," 
    + json.dumps(tool_name) + ","
    + json.dumps(args_summary) + ")"
)
```

**JS side** — `_appendToolCard(id, name, summary)`:
```javascript
window._appendToolCard = function(id, name, summary) {
    ...
    var summaryHtml = summary ? ' &middot; <span class="tool-stream-summary">' + _htmlEscape(summary) + '</span>' : '';
    var card = '<div class="tool-stack-row" id="tool-stack-' + id + '">' +
        '<div class="tool-stack-card">' +
        '<div class="thinking-header">' +
        '<div class="thinking-label">' + _toolIcon(name) + ' ' + _htmlEscape(name) + summaryHtml + '</div>' +
        '<a class="thinking-toggle" href="thalamus://toggle-tool-stack/' + id + '">Hide</a>' +
        '</div>' +
        '<div id="tool-stream-' + id + '" style="padding:2px 8px;"></div>' +
        '</div></div>';
    ...
};
```

This makes the command/args visible immediately during live streaming, not just after re-render.

### Phase 5 — Add CSS for the streaming summary

```css
.tool-stream-summary {
    font-weight: normal;
    font-size: 12px;
    color: var(--meta-text);
    margin-left: 4px;
}
```

## What each phase fixes

| Phase | Fixes | Affects |
|-------|-------|---------|
| 1 | Per-item toggle visible and clickable | CSS |
| 2 | Summary hides when item body is expanded | CSS + Python `data-expanded` attr |
| 3 | Toggle JS sets `data-expanded` and updates link text | JS in `_on_tool_stack_item_toggle_requested` |
| 4 | Live streaming shows command summary | JS `_appendToolCard` + Python `upsert_tool_event` |
| 5 | Styling for streaming summary | CSS |

## Result

After all phases:

**Live streaming:**
```
┌──────────────────────────────────────────┐
│ 💻 bash · ls -la [Hide]                   │  ← summary visible immediately
│ total 48                                  │
│ drwxr-xr-x ...                            │
└──────────────────────────────────────────┘
```

**History, collapsed (items hidden):**
```
┌────────────────────────────────────┐
│ 🔧 bash [Show]                      │
└────────────────────────────────────┘
```

**History, items visible, collapsed:**
```
┌──────────────────────────────────────────┐
│ 🔧 bash [Hide]                            │
│  ┌────────────────────────────────────┐   │
│  │ bash | ls -la | [Show] | complete  │   │  ← summary + clickable toggle
│  └────────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

**History, items visible, expanded:**
```
┌──────────────────────────────────────────┐
│ 🔧 bash [Hide]                            │
│  ┌────────────────────────────────────┐   │
│  │ bash | [Hide] | complete           │   │  ← summary hidden, toggle visible
│  │  Arguments:                        │   │
│  │  {"command": "ls -la"}              │   │
│  │  Output:                           │   │
│  │  total 48                           │   │
│  │  drwxr-xr-x ...                     │   │
│  └────────────────────────────────────┘   │
└──────────────────────────────────────────┘
```
