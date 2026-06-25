from __future__ import annotations

from typing import List, Dict, Optional, Any
from html import escape
import re
import json
from urllib.parse import quote, unquote

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QEvent, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineCore import QWebEnginePage

from markdown_it import MarkdownIt

# Math support (installed on Arch as python-mdit-py-plugins)
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin
from mdit_py_plugins.amsmath import amsmath_plugin


# Single shared Markdown parser instance.
#
# IMPORTANT:
# - We enable math parsing at the Markdown stage (no regex escaping workarounds).
# - We use:
#   * dollarmath_plugin for $...$ and $$...$$
#   * texmath_plugin(delimiters="brackets") for \(...\) and \[...\]
#   * amsmath_plugin for top-level \begin{align}...\end{align} etc.
_md = (
    MarkdownIt("commonmark", {"html": True})
    .enable("table")
    .use(dollarmath_plugin)
    .use(texmath_plugin, delimiters="brackets")
    .use(amsmath_plugin)
)


# ── CSS template for page navigation dividers ───────────────────
_PAGE_NAV_CSS = """
/* Page navigation */
.page-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 16px 0;
}
.page-divider::before,
.page-divider::after {
    content: '';
    flex: 1;
    border-top: 2px dashed var(--border);
}
.page-nav-prev, .page-nav-next {
    color: var(--meta-text);
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    padding: 2px 8px;
}
.page-nav-prev:hover, .page-nav-next:hover {
    color: var(--text);
    text-decoration: underline;
}
.page-nav-label {
    font-size: 13px;
    color: var(--meta-text);
    white-space: nowrap;
}
.page-nav-goto {
    width: 3em;
    font-size: 13px;
    text-align: center;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 4px;
}
"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
:root {
    /* THEME_VARS */
}

body {
    margin: 0;
    padding: 8px;
    background-color: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
                 sans-serif;
    font-size: 16px;
    line-height: 1.4;
}
body[data-ready="0"] {
    visibility: hidden;
}
.chat-container {
    max-width: 900px;
    margin: 0 auto;
}

/* Message rows: user left, assistant right */
.message-row {
    display: flex;
    margin: 6px 0;
}
.message-row.user {
    justify-content: flex-start;
}
.message-row.assistant {
    justify-content: flex-end;
}

.tool-stack-row {
    display: flex;
    justify-content: center;
    margin: 4px 0;
}

.tool-stack-card {
    width: min(100%, 900px);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 6px 12px;
    background: rgba(255, 248, 240, 0.85);
    color: var(--text);
    font-size: 13px;
    line-height: 1.35;
}

.tool-stack-pending {
    margin-top: 8px;
    border: 1px solid #b36b00;
    background: #fff5db;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 13px;
}

.tool-stack-items {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.tool-stack-item {
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 8px;
    background: white;
    padding: 8px 10px;
}

.tool-stack-item-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}

.tool-stack-item-title {
    font-weight: 600;
}

/* Per-item toggle hidden — one-click expansion shows everything */
.tool-stack-item-toggle {
    display: none;
}

/* Compact arg summary between title and toggle (hidden by default,
   shown via CSS when the item body is collapsed). */
.tool-stack-item-summary {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    color: var(--meta-text);
    margin: 0 8px;
}

.tool-stack-badge {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 999px;
    color: white;
    flex: 0 0 auto;
}

.tool-stack-badge.running { background: #546e7a; }
.tool-stack-badge.ok { background: #2e7d32; }
.tool-stack-badge.error { background: #c62828; }
.tool-stack-badge.denied { background: #6a1b9a; }
.tool-stack-badge.pending { background: #ef6c00; }

.tool-stack-item-meta {
    margin-top: 4px;
    color: var(--meta-text);
    font-size: 11px;
}

.tool-stack-json {
    background: #1e1e1e;
    color: #f5f5f5;
    padding: 8px 10px;
    border-radius: 8px;
    font-family: "Fira Code", "JetBrains Mono", monospace;
    font-size: 12px;
    line-height: 1.35;
    white-space: pre-wrap;
    overflow-x: auto;
    margin: 6px 0 0 0;
}

/* Thinking bubble */
.thinking-row {
    display: flex;
    justify-content: center;
    margin: 4px 0;
}

.thinking-card {
    width: min(100%, 900px);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 6px 12px;
    background: rgba(232, 234, 255, 0.78);
    color: var(--text);
    font-size: 13px;
    line-height: 1.35;
}

.thinking-header {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
}

.thinking-label {
    font-weight: 600;
    color: var(--text);
    flex: 1 1 auto;
}

.thinking-toggle {
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
    flex: 0 0 auto;
}

.thinking-content {
    margin-top: 6px;
    white-space: pre-wrap;
    font-size: 13px;
    line-height: 1.35;
}

/* Speech bubbles */
.bubble {
    border-radius: 14px;
    padding: 8px 12px;
    max-width: 70%;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    font-size: 16px;
    line-height: 1.4;
    word-wrap: break-word;
    white-space: normal;
}
.bubble.user {
    background: var(--bubble-user);
    color: var(--text);
}
.bubble.assistant {
    background: var(--bubble-assistant);
    color: var(--text);
}
.bubble.latest {
    box-shadow:
        0 0 0 3px var(--border),
        0 0 8px rgba(0, 0, 0, 0.35);
}

.meta {
    font-size: 11px;
    color: var(--meta-text);
    margin-bottom: 2px;
}

/* Code blocks */
pre.code-block {
    background: #1e1e1e;
    color: #f5f5f5;
    padding: 8px 10px;
    border-radius: 8px;
    font-family: "Fira Code", "JetBrains Mono", monospace;
    font-size: 16px;
    overflow-x: auto;
    white-space: pre;
    margin: 4px 0;

    position: relative;
    padding-top: 26px;
}
pre.code-block code {
    white-space: pre;
}

/* copy-code button */
.copy-code-btn {
    position: absolute;
    top: 4px;
    right: 6px;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid #555;
    background: #2b2b2b;
    color: #f5f5f5;
    cursor: pointer;
    opacity: 0.8;
}
.copy-code-btn:hover {
    opacity: 1.0;
}
.copy-code-btn:active {
    transform: translateY(1px);
}

/* Images */
.chat-image {
    max-width: 100%;
    border-radius: 6px;
    margin: 4px 0;
}

/* Tables rendered by markdown-it */
table {
    border-collapse: collapse;
    margin: 6px 0;
    font-size: 12px;
    width: 100%;
    display: block;
    overflow-x: auto;
}
th, td {
    border: 1px solid var(--border);
    padding: 4px 8px;
    text-align: left;
    vertical-align: top;
}
th {
    background: rgba(0, 0, 0, 0.04);
    font-weight: 600;
}
tr:nth-child(even) {
    background: rgba(0, 0, 0, 0.02);
}

/* KaTeX rendering targets produced by mdit-py-plugins */
eq, eqn, .math.amsmath {
    display: inline;
}
eqn, .math.amsmath {
    display: block;
    margin: 6px 0;
}

/* Scrollbar theming for QWebEngine (Chromium) */
body::-webkit-scrollbar {
    width: 10px;
}
body::-webkit-scrollbar-track {
    background: var(--bg);
}
body::-webkit-scrollbar-thumb {
    background-color: var(--border);
    border-radius: 5px;
    border: 2px solid var(--bg);
}

/* Agent work collapsible group */
.agent-work-group {
    margin: 4px 0;
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: rgba(240, 240, 244, 0.6);
}

.agent-work-header {
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
    color: var(--meta-text);
    padding: 2px 0;
    user-select: none;
}
.agent-work-header:hover {
    color: var(--text);
}

.agent-work-items {
    margin-top: 4px;
}

/* PAGE_NAV_CSS */
</style>

<!-- KaTeX (system-installed, Arch katex package) -->
<link rel="stylesheet"
      href="file:///usr/lib/node_modules/katex/dist/katex.min.css">
<script defer
        src="file:///usr/lib/node_modules/katex/dist/katex.min.js"></script>

<!-- highlight.js syntax highlighting (system node module) -->
<link rel="stylesheet"
      href="file:///usr/lib/node_modules/@highlightjs/cdn-assets/styles/github-dark.min.css">
<script src="file:///usr/lib/node_modules/@highlightjs/cdn-assets/highlight.min.js"></script>

<script>
function _isAtBottom(tolerancePx) {
    var tol = (typeof tolerancePx === "number") ? tolerancePx : 6;
    var el = document.documentElement;
    return (window.innerHeight + window.scrollY) >= (el.scrollHeight - tol);
}

function _scrollToBottom() {
    var el = document.documentElement;
    window.scrollTo(0, el.scrollHeight);
}

// Scroll-position preservation helpers for toggle actions.
// Usage: var savedY = _saveScrollY();
//        ... DOM changes ...
//        _restoreScrollY(savedY);
function _saveScrollY() {
    return window.scrollY;
}
function _restoreScrollY(y) {
    window.scrollTo(0, y);
}

function prettifyJsonBlocks() {
    var blocks = document.querySelectorAll('pre.code-block code.language-json');
    blocks.forEach(function(block) {
        try {
            var text = block.textContent;
            var trimmed = text.trim();
            if (!trimmed) return;
            var obj = JSON.parse(trimmed);
            var pretty = JSON.stringify(obj, null, 2);
            if (pretty !== text) {
                block.textContent = pretty;
            }
        } catch (e) {
            // If it's not valid JSON, leave it as-is
        }
    });
}

function highlightCodeBlocks() {
    if (typeof hljs === "undefined") {
        return;
    }
    var blocks = document.querySelectorAll('pre.code-block > code');
    blocks.forEach(function(block) {
        hljs.highlightElement(block);
    });
}

function enhanceCodeBlocks() {
    var blocks = document.querySelectorAll('pre.code-block');
    blocks.forEach(function(pre) {
        if (pre.querySelector('.copy-code-btn')) {
            return;
        }

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'copy-code-btn';
        button.textContent = 'Copy';

        button.addEventListener('click', function(ev) {
            ev.stopPropagation();
            var code = pre.querySelector('code');
            var text = code ? code.textContent : pre.textContent;
            // Show feedback immediately, then trigger clipboard copy
            // via a custom URL navigation intercepted by acceptNavigationRequest.
            // location.href is more reliable than createElement('a').click()
            // in QWebEngineView, which lacks user activation for synthetic clicks.
            var old = button.textContent;
            button.textContent = 'Copied!';
            setTimeout(function() { button.textContent = old; }, 1200);
            location.href = 'thalamus://copy/' + encodeURIComponent(text);
        });

        pre.appendChild(button);
    });
}

/**
 * Attach click handlers to agent-work headers to toggle collapsed/expanded.
 */
function enhanceAgentWorkGroups() {
    var headers = document.querySelectorAll('.agent-work-header');
    headers.forEach(function(header) {
        if (header.hasAttribute('data-agent-work-ready')) return;
        header.setAttribute('data-agent-work-ready', '1');
        header.addEventListener('click', function(ev) {
            ev.stopPropagation();
            var group = this.parentElement;
            var items = group.querySelector('.agent-work-items');
            if (!items) return;
            var isExpanded = items.style.display !== 'none';
            if (isExpanded) {
                items.style.display = 'none';
                group.classList.add('collapsed');
                group.classList.remove('expanded');
                // Update header icon.
                var node = this.firstChild;
                if (node && node.nodeType === 3) {
                    var s = node.textContent || '';
                    node.textContent = s.replace('▼', '▶');
                }
            } else {
                items.style.display = '';
                group.classList.add('expanded');
                group.classList.remove('collapsed');
                var node = this.firstChild;
                if (node && node.nodeType === 3) {
                    var s = node.textContent || '';
                    node.textContent = s.replace('▶', '▼');
                }
            }
        });
    });
}

/**
 * Render math from mdit-py-plugins output nodes.
 *
 * The math plugins emit:
 *  - inline math as: <eq>...</eq>
 *  - display math as: <eqn>...</eqn> (often inside <section> wrappers)
 *  - amsmath environments as: <div class="math amsmath">...</div>
 *
 * We render these nodes using katex.render() directly, so we do NOT depend on
 * delimiter scanning and we avoid delimiter/backslash escaping issues.
 */
function renderMathNodes() {
    if (typeof katex === "undefined" || !katex.render) {
        return;
    }

    function renderNode(el, displayMode) {
        if (!el) return;
        // Capture raw TeX from textContent BEFORE we mutate the DOM.
        var tex = el.textContent || "";
        // Clear before render so katex can replace cleanly.
        el.innerHTML = "";
        try {
            katex.render(tex, el, {
                displayMode: displayMode,
                throwOnError: false
            });
        } catch (e) {
            // If KaTeX fails, fall back to showing the raw TeX.
            el.textContent = tex;
        }
    }

    // Inline: <eq>
    var inlines = document.getElementsByTagName("eq");
    // HTMLCollection is live; copy to array first.
    Array.from(inlines).forEach(function(el) { renderNode(el, false); });

    // Display: <eqn>
    var displays = document.getElementsByTagName("eqn");
    Array.from(displays).forEach(function(el) { renderNode(el, true); });

    // AMS environments: <div class="math amsmath">
    var ams = document.querySelectorAll("div.math.amsmath");
    ams.forEach(function(el) { renderNode(el, true); });
}

/**
 * Append streaming text into an existing assistant message element.
 *
 * Streaming is intentionally plain text (no markdown/math render) to avoid page reloads.
 * At stream end, Python does a single full render, which runs renderMathNodes().
 */
window.thalamusAppendAssistantDelta = function(targetId, deltaText) {
    try {
        var atBottom = _isAtBottom(8);
        var el = document.getElementById(targetId);
        if (!el) return false;

        el.appendChild(document.createTextNode(deltaText));

        if (atBottom) {
            setTimeout(function() { _scrollToBottom(); }, 0);
        }
        return true;
    } catch (e) {
        return false;
    }
}

/**
 * Append streaming thinking text into a thinking bubble element.
 */
window.thalamusAppendThinkingDelta = function(targetId, deltaText) {
    try {
        var atBottom = _isAtBottom(8);
        var el = document.getElementById(targetId);
        if (!el) return false;

        el.appendChild(document.createTextNode(deltaText));

        if (atBottom) {
            setTimeout(function() { _scrollToBottom(); }, 0);
        }
        return true;
    } catch (e) {
        return false;
    }
}

/**
 * Streaming DOM helpers — append/update nodes without full page reload.
 */

window._appendMessage = function(html) {
    try {
        var atBottom = _isAtBottom(8);
        var container = document.querySelector('.chat-container');
        if (!container) return false;
        container.insertAdjacentHTML('beforeend', html);
        if (atBottom) { setTimeout(function() { _scrollToBottom(); }, 0); }
        return true;
    } catch(e) { return false; }
};

window._appendUserBubble = function(text) {
    return _appendMessage(
        '<div class="message-row user">' +
        '  <div class="bubble user">' + text + '</div>' +
        '</div>'
    );
};

window._ensureAgentWorkGroup = function() {
    var groups = document.querySelectorAll('.agent-work-group');
    var last = groups.length ? groups[groups.length - 1] : null;
    if (last) {
        // Check if this group is already closed (followed by assistant text).
        var next = last.nextElementSibling;
        if (next && next.classList.contains('message-row')) {
            last = null;
        }
    }
    if (!last) {
        var html = '<div class="agent-work-group expanded" id="agent-work-live">' +
            '<div class="agent-work-header" data-agent-work-ready="1">▼ Agent work (0 items)</div>' +
            '<div class="agent-work-items"></div></div>';
        var container = document.querySelector('.chat-container');
        if (container) {
            container.insertAdjacentHTML('beforeend', html);
            last = document.getElementById('agent-work-live');
        }
    }
    return last;
};

window._updateWorkGroupCount = function(group) {
    if (!group) return;
    var items = group.querySelector('.agent-work-items');
    if (!items) return;
    var count = items.children.length;
    var header = group.querySelector('.agent-work-header');
    if (header) {
        header.textContent = '▼ Agent work (' + count + ' item' + (count !== 1 ? 's' : '') + ')';
    }
};

window._appendToolCard = function(id, name) {
    try {
        var atBottom = _isAtBottom(8);
        var group = _ensureAgentWorkGroup();
        if (!group) return false;
        var items = group.querySelector('.agent-work-items');
        if (!items) return false;
        var card = '<div class="tool-stack-row" id="tool-stack-' + id + '">' +
            '<div class="tool-stack-card">' +
            '<div class="thinking-header">' +
            '<div class="thinking-label">' + _toolIcon(name) + ' ' + _htmlEscape(name) + '</div>' +
            '<a class="thinking-toggle" href="thalamus://toggle-tool-stack/' + id + '">Hide</a>' +
            '</div>' +
            '<div id="tool-stream-' + id + '" style="padding:2px 8px;"></div>' +
            '</div></div>';
        items.insertAdjacentHTML('beforeend', card);
        _updateWorkGroupCount(group);
        group.classList.add('expanded'); group.classList.remove('collapsed');
        if (atBottom) { setTimeout(function() { _scrollToBottom(); }, 0); }
        return true;
    } catch(e) { return false; }
};

window._htmlEscape = function(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
};

window._appendToolText = function(id, text) {
    try {
        var el = document.getElementById('tool-stream-' + id);
        if (!el) return false;
        el.textContent = text;
        return true;
    } catch(e) { return false; }
};

window._finalizeToolCard = function(id, resultHtml, isError) {
    try {
        var el = document.getElementById('tool-stream-' + id);
        if (!el) return false;
        var cls = isError ? 'tool-result-error' : 'tool-result';
        el.innerHTML = '<div class="' + cls + '">' + resultHtml + '</div>';
        return true;
    } catch(e) { return false; }
};

window._closeAgentWorkGroup = function() {
    var group = document.getElementById('agent-work-live');
    if (group) {
        group.classList.add('collapsed'); group.classList.remove('expanded');
        group.removeAttribute('id');
    }
};

window._beginAssistantBubble = function() {
    try {
        var atBottom = _isAtBottom(8);
        _closeAgentWorkGroup();
        var html = '<div class="message-row assistant">' +
            '<div class="bubble assistant latest">' +
            '<div id="assistant-stream-content" style="white-space: pre-wrap;"></div>' +
            '</div></div>';
        var container = document.querySelector('.chat-container');
        if (!container) return false;
        container.insertAdjacentHTML('beforeend', html);
        if (atBottom) { setTimeout(function() { _scrollToBottom(); }, 0); }
        // Remove 'latest' from previous assistant bubble
        var prevAssistant = container.querySelectorAll('.bubble.assistant.latest');
        for (var i = 0; i < prevAssistant.length - 1; i++) {
            prevAssistant[i].classList.remove('latest');
        }
        return true;
    } catch(e) { return false; }
};

// Tool icon lookup (same as Python _tool_icon)
window._toolIcons = {
    'read': '📖', 'bash': '💻', 'write': '✏️', 'edit': '📝',
    'grep': '🔍', 'find': '🔎', 'ls': '📂',
    'mempalace_search': '🧠', 'mempalace_remember': '💾',
    'mempalace_open_loops': '📋', 'mempalace_status': 'ℹ️',
    'mempalace_search': '🔍', 'mempalace_diary_read': '📖'
};
window._toolIcon = function(name) {
    var base = name.split('.').pop() || name;
    return window._toolIcons[base] || '🛠️';
};

// ── page navigation go-to handler ──────────────────────────────
function _handleGoToPage(inputEl, totalPages) {
    var val = parseInt(inputEl.value, 10);
    if (isNaN(val) || val < 1) return;
    var pageIdx = Math.min(val - 1, totalPages - 1);
    location.href = 'thalamus://navigate-page/' + pageIdx;
}

document.addEventListener("DOMContentLoaded", function() {
    prettifyJsonBlocks();
    highlightCodeBlocks();
    enhanceCodeBlocks();
    enhanceAgentWorkGroups();
    renderMathNodes();

    if (document.body.getAttribute("data-scroll") === "1") {
        _scrollToBottom();
    }
    requestAnimationFrame(function() {
        document.body.setAttribute("data-ready", "1");
    });
});
</script>
</head>

<body data-ready="0" data-scroll="{scroll}">
<div class="chat-container">
{messages_html}
</div>
</body>
</html>
"""


# ── Page navigation HTML builder ──────────────────────────────────


def _page_nav_html(
    display_start: int,
    display_end: int,
    total_pages: int,
) -> str:
    """Build a page navigation bar with Prev/Next buttons, page counter, and Go-to input."""
    has_prev = display_start > 0
    has_next = display_end < total_pages - 1
    prev_page = display_start - 1 if has_prev else -1
    next_page = display_end + 1 if has_next else -1

    prev_html = (
        f'<a class="page-nav-prev" href="thalamus://navigate-page/{prev_page}">◀ Prev</a>'
        if has_prev
        else '<span class="page-nav-prev" style="visibility:hidden">◀ Prev</span>'
    )
    next_html = (
        f'<a class="page-nav-next" href="thalamus://navigate-page/{next_page}">Next ▶</a>'
        if has_next
        else '<span class="page-nav-next" style="visibility:hidden">Next ▶</span>'
    )

    if display_start == display_end:
        label = f"Page {display_start + 1} / {total_pages}"
    else:
        label = f"Pages {display_start + 1}–{display_end + 1} / {total_pages}"

    goto = (
        f'<input class="page-nav-goto" type="text" placeholder="Go" '
        f'onkeydown="if(event.key===\'Enter\')'
        f'{{_handleGoToPage(this,{total_pages})}}" />'
    )

    return (
        f'<div class="page-divider">'
        f'{prev_html}'
        f'<span class="page-nav-label">{label}</span>'
        f'{next_html}'
        f'{goto}'
        f'</div>'
    )


class _ChatPage(QWebEnginePage):
    toolStackToggleRequested = Signal(str)
    toolStackItemToggleRequested = Signal(str, str)
    thinkingToggleRequested = Signal(int)
    copyRequested = Signal(str)
    navigatePageRequested = Signal(int)

    def createWindow(self, _type):
        # Tool stack controls are handled in-page; never spawn a second WebEngine window.
        return self

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "thalamus" and url.host() == "toggle-tool-stack":
            stack_id = url.path().lstrip("/")
            if stack_id:
                self.toolStackToggleRequested.emit(stack_id)
            return False
        if url.scheme() == "thalamus" and url.host() == "toggle-thinking":
            index_str = url.path().lstrip("/")
            try:
                idx = int(index_str)
                self.thinkingToggleRequested.emit(idx)
            except ValueError:
                pass
            return False
        if url.scheme() == "thalamus" and url.host() == "toggle-tool-item":
            parts = [unquote(part) for part in url.path().split("/") if part]
            if len(parts) == 2:
                stack_id, item_key = parts
                if stack_id and item_key:
                    self.toolStackItemToggleRequested.emit(stack_id, item_key)
            return False
        if url.scheme() == "thalamus" and url.host() == "copy":
            text = unquote(url.path().lstrip("/"))
            if text:
                self.copyRequested.emit(text)
            return False
        if url.scheme() == "thalamus" and url.host() == "navigate-page":
            try:
                page = int(url.path().lstrip("/"))
                self.navigatePageRequested.emit(page)
            except ValueError:
                pass
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


# ── Markdown / rendering helpers ───────────────────────────────────


def _split_out_code_fences(markdown: str) -> List[str]:
    """Split a markdown string into segments, preserving fenced code blocks."""
    parts: List[str] = []
    fence = re.compile(r"```(.*?)```", re.DOTALL)
    last = 0
    for m in fence.finditer(markdown):
        if m.start() > last:
            parts.append(markdown[last:m.start()])
        parts.append(markdown[m.start():m.end()])
        last = m.end()
    if last < len(markdown):
        parts.append(markdown[last:])
    return parts


def format_content_to_html(content: str) -> str:
    """Convert markdown content to HTML with fenced code blocks rendered as <pre>."""
    segments = _split_out_code_fences(content)
    out: List[str] = []

    fence_re = re.compile(r"^```(\w+)?\n(.*)\n```$", re.DOTALL)

    for seg in segments:
        seg = seg or ""
        m = fence_re.match(seg.strip())
        if m:
            lang = (m.group(1) or "").strip().lower()
            code = m.group(2) or ""
            code_html = escape(code)

            lang_class = f" language-{lang}" if lang else ""
            out.append(
                f'<pre class="code-block"><code class="{lang_class}">{code_html}</code></pre>'
            )
        else:
            out.append(_md.render(seg))

    return "".join(out)


def _format_json_block(value: Any) -> str:
    try:
        formatted = json.dumps(value, ensure_ascii=False, indent=2)
        # Unescape common JSON escapes so long strings (task descriptions,
        # code output) are readable in the <pre> block.
        formatted = formatted.replace("\\n", "\n")
        formatted = formatted.replace("\\t", "\t")
        return escape(formatted)
    except Exception:
        return escape(str(value))


def _tool_item_status_label(item: Dict[str, Any]) -> tuple[str, str]:
    status = str(item.get("status") or "running")
    if status == "ok":
        return ("complete", "ok")
    if status == "pending_approval":
        return ("awaiting approval", "pending")
    if status == "denied":
        return ("denied", "denied")
    if status == "error":
        return ("failed", "error")
    return ("running", "running")


def _tool_item_title(item: Dict[str, Any]) -> str:
    item_kind = str(item.get("item_kind") or "tool")
    if item_kind == "node":
        return str(item.get("node_id") or item.get("tool_name") or "node")
    return str(item.get("tool_name") or "tool")


def _tool_icon(tool_name: str) -> str:
    """Return an emoji icon for a tool name."""
    icons = {
        "bash": "&#x1f5a5;",       # 🖥
        "read": "&#x1f4c4;",       # 📄
        "write": "&#x1f4dd;",      # 📝
        "edit": "&#x270f;",        # ✏
        "grep": "&#x1f50d;",       # 🔍
        "ls": "&#x1f4c1;",        # 📁
        "find": "&#x1f50e;",       # 🔎
        "subagent": "&#x1f916;",   # 🤖
    }
    return icons.get(tool_name, "&#x1f527;")  # 🔧 default


def _tool_args_summary(item: Dict[str, Any]) -> str:
    """Extract a compact one-line summary from the tool arguments."""
    args = item.get("args")
    if not isinstance(args, dict):
        return ""
    tool_name = str(item.get("tool_name", "") or "")
    if tool_name == "bash":
        cmd = args.get("command", "")
        if isinstance(cmd, str):
            return cmd[:120]
    elif tool_name == "read":
        p = args.get("path", "")
        if isinstance(p, str):
            return p[:120]
    elif tool_name == "write":
        p = args.get("path", "")
        if isinstance(p, str):
            return p[:120]
    elif tool_name == "edit":
        p = args.get("path", "")
        if isinstance(p, str):
            # Include a snippet of oldText if it's short.
            old = args.get("oldText", "")
            if isinstance(old, str) and len(old) < 60:
                return f"{p[:80]} \u2190 {old[:40]}"
            return p[:120]
    elif tool_name == "grep":
        pattern = args.get("pattern", "")
        if isinstance(pattern, str):
            return f"grep {pattern[:80]}"
    elif tool_name == "subagent":
        task = args.get("task", "")
        if isinstance(task, str):
            return task[:120]
    # Fallback: first value from the args dict.
    for v in args.values():
        if isinstance(v, str) and v:
            return v[:120]
        if isinstance(v, (int, float)):
            return str(v)[:120]
    return ""


def _fmt_tokens(count: int) -> str:
    """Format a token count with k / M suffix (duplicated from main_window for standalone use)."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)


def _format_subagent_details(details: dict) -> str:
    """Format subagent result details into a compact info line."""
    results = details.get("results", [])
    if not isinstance(results, list) or len(results) == 0:
        return ""
    r = results[0]
    if not isinstance(r, dict):
        return ""

    parts: list[str] = []
    agent = str(r.get("agent") or "")
    if agent:
        parts.append(f"&#x1f916; {escape(agent)}")
    model = str(r.get("model") or "")
    if model:
        parts.append(escape(model.split("/")[-1] if "/" in model else model))
    turns = r.get("turns")
    if isinstance(turns, (int, float)) and turns > 0:
        parts.append(f"{int(turns)} turn{'s' if int(turns) != 1 else ''}")
    usage = r.get("usage")
    if isinstance(usage, dict):
        inp = int(usage.get("input", 0) or 0)
        out = int(usage.get("output", 0) or 0)
        cr = int(usage.get("cacheRead", 0) or 0)
        if inp + out + cr > 0:
            usage_parts: list[str] = []
            if inp:
                usage_parts.append(f"↑{_fmt_tokens(inp)}")
            if out:
                usage_parts.append(f"↓{_fmt_tokens(out)}")
            if cr:
                usage_parts.append(f"R{_fmt_tokens(cr)}")
            parts.append(" ".join(usage_parts))
    return " · ".join(parts)


def _render_tool_stack_item(item: Dict[str, Any]) -> str:
    tool_name = _tool_item_title(item)
    status_label, badge_class = _tool_item_status_label(item)
    stack_id = str(item.get("stack_id") or "")
    item_key = str(item.get("item_key") or "")
    expanded = bool(item.get("expanded", False))
    meta_parts: list[str] = []
    item_kind = str(item.get("item_kind") or "tool")
    if item_kind == "node":
        meta_parts.append("node")
    if item.get("tool_kind"):
        meta_parts.append(str(item.get("tool_kind")))
    if item.get("mcp_server_id"):
        meta_parts.append(str(item.get("mcp_server_id")))
    if item.get("step") is not None:
        meta_parts.append(f"step {item.get('step')}")
    meta_html = ""
    if meta_parts:
        meta_html = f'<div class="tool-stack-item-meta">{escape(" · ".join(meta_parts))}</div>'

    body_parts: list[str] = []
    if item.get("description") and str(item.get("status") or "") == "pending_approval":
        body_parts.append(f"<div>{escape(str(item.get('description') or ''))}</div>")
    if item.get("error"):
        body_parts.append(f"<div>{escape(str(item.get('error') or ''))}</div>")
    body_style = "" if expanded else ' style="display:none"'
    if "_fmt_details" in item:
        body_parts.append(
            f'<div class="tool-stack-item-meta" style="margin-top:0;">'
            f'{item["_fmt_details"]}'
            '</div>'
        )
    if "_fmt_args" in item:
        body_parts.append("<div>Arguments</div>")
        body_parts.append(f'<pre class="tool-stack-json">{item["_fmt_args"]}</pre>')
    if "_fmt_stream" in item:
        body_parts.append("<div>Output</div>")
        body_parts.append(f'<pre class="tool-stack-json">{item["_fmt_stream"]}</pre>')
    if "_fmt_result" in item:
        body_parts.append("<div>Result</div>")
        body_parts.append(f'<pre class="tool-stack-json">{item["_fmt_result"]}</pre>')

    actions_html = ""
    request_id = str(item.get("request_id") or "")
    if str(item.get("status") or "") == "pending_approval" and request_id and stack_id:
        approve_href = (
            "thalamus://tool-approval/approve-once/"
            f"{quote(stack_id, safe='')}/{quote(request_id, safe='')}"
        )
        deny_href = (
            "thalamus://tool-approval/deny-once/"
            f"{quote(stack_id, safe='')}/{quote(request_id, safe='')}"
        )
        always_allow_href = (
            "thalamus://tool-approval/always-allow/"
            f"{quote(stack_id, safe='')}/{quote(request_id, safe='')}"
        )
        always_deny_href = (
            "thalamus://tool-approval/always-deny/"
            f"{quote(stack_id, safe='')}/{quote(request_id, safe='')}"
        )
        persistent_actions_html = ""
        if str(item.get("tool_kind") or "") == "mcp" and str(item.get("mcp_server_id") or ""):
            persistent_actions_html = (
                f'<a class="tool-stack-action approve" href="{always_allow_href}">Always allow</a>'
                f'<a class="tool-stack-action deny" href="{always_deny_href}">Always deny</a>'
            )
        actions_html = (
            '<div class="tool-stack-actions">'
            f'<a class="tool-stack-action approve" href="{approve_href}">Approve once</a>'
            f'<a class="tool-stack-action deny" href="{deny_href}">Deny once</a>'
            f'{persistent_actions_html}'
            '</div>'
        )

    body_html = ""
    if body_parts or actions_html:
        body_html = f'<div class="tool-stack-item-body"{body_style}>{"".join(body_parts)}{actions_html}</div>'

    # Compact summary shown when collapsed (class hidden by default,
    # revealed via CSS when the item-body is hidden).
    args_summary = _tool_args_summary(item)
    summary_html = (
        f'<span class="tool-stack-item-summary">{escape(args_summary)}</span>'
        if args_summary
        else ''
    )

    return (
        f'<div class="tool-stack-item" data-item-key="{escape(item_key)}">' 
        '  <div class="tool-stack-item-header">'
        f'    <div class="tool-stack-item-title">{escape(tool_name)}</div>'
        f'    {summary_html}'
        f'    <a class="tool-stack-item-toggle" href="thalamus://toggle-tool-item/{quote(stack_id, safe="")}/{quote(item_key, safe="")}">{"Hide" if expanded else "Show"}</a>'
        f'    <div class="tool-stack-badge {badge_class}">{escape(status_label)}</div>'
        '  </div>'
        f'{meta_html}'
        f'{body_html}'
        '</div>'
    )


def _render_tool_stack_div(msg: dict, stack_id: str, parts_out: list) -> None:
    """Render a single tool_stack message into *parts_out*."""
    expanded = bool(msg.get("expanded", False))
    items = [it for it in msg.get("items", []) if isinstance(it, dict)]
    pending_item = next((it for it in items if str(it.get("status") or "") == "pending_approval"), None)

    first_item = next(
        (it for it in items if str(it.get("item_kind") or "") != "node"),
        items[0] if items else None,
    )
    tool_name = str(first_item.get("tool_name") or "tool") if first_item else "tool"
    tool_icon = _tool_icon(tool_name)

    header_html = (
        '<div class="thinking-header">'
        f'<div class="thinking-label">{tool_icon} {escape(tool_name)}</div>'
        f'<a class="thinking-toggle" '
        f'href="thalamus://toggle-tool-stack/{escape(stack_id)}">'
        f'{"Hide" if expanded else "Show"}'
        '</a>'
        '</div>'
    )

    pending_html = ""
    if pending_item is not None:
        pending_html = (
            '<div class="tool-stack-pending">'
            f'{_render_tool_stack_item(pending_item)}'
            '</div>'
        )
    rendered_items = []
    for item in items:
        if pending_item is not None and item is pending_item:
            continue
        rendered_items.append(_render_tool_stack_item(item))
    if rendered_items:
        display_style = '' if expanded else ' style="display:none"'
        items_html = f'<div class="tool-stack-items"{display_style}>{"".join(rendered_items)}</div>'
    else:
        items_html = ""
    stack_id_esc = escape(stack_id)
    parts_out.append(
        f'<div class="tool-stack-row" id="tool-stack-{stack_id_esc}">'
        f'  <div class="tool-stack-card">{header_html}{pending_html}{items_html}</div>'
        '</div>'
    )


def _render_thinking_div(msg: dict, idx: int, thinking_stream_index: int | None, parts_out: list) -> None:
    """Render a single thinking message into *parts_out*."""
    thinking_text = str(msg.get("text", "") or "")
    expanded = bool(msg.get("expanded", False))

    header_html = (
        '<div class="thinking-header">'
        f'<div class="thinking-label">&#x1F4AD; Thinking</div>'
        f'<a class="thinking-toggle" '
        f'href="thalamus://toggle-thinking/{idx}">'
        f'{"Hide" if expanded else "Show"}'
        '</a>'
        '</div>'
    )

    if thinking_stream_index is not None and idx == thinking_stream_index:
        content_html = (
            f'<div id="thinking-stream-content-{idx}" '
            f'class="thinking-content">{escape(thinking_text)}</div>'
        )
    else:
        display_style = '' if expanded else ' style="display:none"'
        content_html = (
            f'<div class="thinking-content"{display_style}>'
            f'{escape(thinking_text)}'
            f'</div>'
        )

    parts_out.append(
        f'<div class="thinking-row" id="thinking-{idx}">'
        f'  <div class="thinking-card">{header_html}{content_html}</div>'
        '</div>'
    )


def _flush_agent_work_group(
    group_items: list[tuple[str, int, dict]],
    parts_out: list,
    thinking_stream_index: int | None,
    is_last: bool = False,
) -> None:
    """Render accumulated thinking/tool items as an 'agent-work' collapsible group."""
    if not group_items:
        return

    count = len(group_items)
    # The group is expanded (visible) if the active thinking stream index falls
    # anywhere inside it, OR if this is the last group and the agent is still
    # working (thinking just ended but tools/subagents may still be streaming).
    expanded = is_last or any(
        thinking_stream_index is not None and idx == thinking_stream_index
        for _, idx, _ in group_items
    )

    inner_parts: list[str] = []
    for kind, idx, msg in group_items:
        if kind == "thinking":
            _render_thinking_div(msg, idx, thinking_stream_index, inner_parts)
        else:
            stack_id = str(msg.get("stack_id", str(idx)))
            _render_tool_stack_div(msg, stack_id, inner_parts)

    header_icon = "▼" if expanded else "▶"
    items_display = "" if expanded else "display:none"

    parts_out.append(
        f'<div class="agent-work-group{" expanded" if expanded else " collapsed"}"'
        f'  id="agent-work-{id(group_items)}">'
        f'  <div class="agent-work-header">'
        f'    {header_icon} Agent work ({count} item{"s" if count != 1 else ""})'
        f'  </div>'
        f'  <div class="agent-work-items" style="{items_display}">'
        f'    {"".join(inner_parts)}'
        f'  </div>'
        f'</div>'
    )


NON_TURN_KINDS = frozenset({"thinking", "tool_stack", "activity"})


# ── Core message-to-HTML rendering (page-aware) ──────────────────


def _messages_to_html(
    messages: List[Dict[str, Any]],
    assistant_stream_index: int | None = None,
    thinking_stream_index: int | None = None,
    page_start: int = 0,
    page_end: int | None = None,
) -> str:
    """Render message list to inner HTML — no document wrapper, no theme/scrolling.

    When *page_end* is not None, only messages in [page_start, page_end) are rendered.
    """
    if page_end is None:
        page_end = len(messages)

    parts: List[str] = []

    # Accumulator for consecutive thinking / tool_stack / activity items.
    agent_work_buffer: list[tuple[str, int, dict]] = []

    for i in range(page_start, min(page_end, len(messages))):
        msg = messages[i]
        kind = str(msg.get("kind", "turn") or "turn")
        content = str(msg.get("content", "") or "")
        meta = msg.get("meta")

        if kind in NON_TURN_KINDS:
            agent_work_buffer.append((kind, i, msg))
            continue

        # Flush any buffered agent work before a turn row.
        _flush_agent_work_group(agent_work_buffer, parts, thinking_stream_index)
        agent_work_buffer.clear()

        role = str(msg.get("role", "user") or "user")

        role_class = "user" if role == "human" else "assistant"
        bubble_class = "user" if role == "human" else "assistant"

        bubble_class_attr = f"bubble {bubble_class}"
        if i == len(messages) - 1:
            bubble_class_attr += " latest"

        # During streaming, we want a stable DOM node to append plain text into.
        if assistant_stream_index is not None and i == assistant_stream_index:
            body_html = (
                f'<div id="assistant-stream-content" '
                f'style="white-space: pre-wrap;">{escape(content)}</div>'
            )
        else:
            body_html = format_content_to_html(content)

        meta_html = ""
        if meta:
            meta_html = f'<div class="meta">{escape(meta)}</div>'

        parts.append(
            f'<div class="message-row {role_class}">'
            f'  <div class="{bubble_class_attr}">'
            f'{meta_html}{body_html}'
            f'  </div>'
            f'</div>'
        )

    # Flush remaining agent work.
    _flush_agent_work_group(agent_work_buffer, parts, thinking_stream_index, is_last=True)

    return "\n".join(parts)


def _build_html_document(
    inner_html: str,
    theme: Optional[Dict[str, str]] = None,
    scroll_to_bottom: bool = True,
) -> str:
    """Wrap inner HTML in the full HTML_TEMPLATE with theme variables and scroll flag."""
    defaults = {
        "bg": "#f5f5f7",
        "text": "#000000",
        "bubble_user": "#e3f2fd",
        "bubble_assistant": "#ffffff",
        "meta_text": "#666666",
        "border": "#cccccc",
    }

    colors = defaults.copy()
    if theme:
        for key, value in theme.items():
            if key in colors and isinstance(value, str) and value.startswith("#"):
                colors[key] = value

    theme_vars_lines = [
        f"    --bg: {colors['bg']};",
        f"    --text: {colors['text']};",
        f"    --bubble-user: {colors['bubble_user']};",
        f"    --bubble-assistant: {colors['bubble_assistant']};",
        f"    --meta-text: {colors['meta_text']};",
        f"    --border: {colors['border']};",
    ]
    theme_vars = "\n".join(theme_vars_lines)

    html = HTML_TEMPLATE.replace("/* THEME_VARS */", theme_vars)
    html = html.replace("/* PAGE_NAV_CSS */", _PAGE_NAV_CSS)
    html = html.replace("{messages_html}", inner_html)
    scroll_attr = "1" if scroll_to_bottom else "0"
    html = html.replace("{scroll}", scroll_attr)
    return html


# ── Backward-compatible wrapper ──────────────────────────────────


def render_chat_html(
    messages: List[Dict[str, Any]],
    theme: Optional[Dict[str, str]] = None,
    assistant_stream_index: int | None = None,
    thinking_stream_index: int | None = None,
    scroll_to_bottom: bool = True,
    body_html_cache: dict[int, str] | None = None,
) -> str:
    """Render all messages to a full HTML document.

    This is the backward-compatible wrapper. For paginated rendering,
    use ``_messages_to_html()`` + ``_build_html_document()`` directly.
    """
    inner = _messages_to_html(
        messages,
        assistant_stream_index=assistant_stream_index,
        thinking_stream_index=thinking_stream_index,
    )
    return _build_html_document(inner, theme=theme, scroll_to_bottom=scroll_to_bottom)


# ═══════════════════════════════════════════════════════════════════
#  ChatRenderer — paginated QWebEngineView wrapper
# ═══════════════════════════════════════════════════════════════════


class ChatRenderer(QWidget):
    """A small wrapper around QWebEngineView that renders chat bubbles via HTML.

    Messages are divided into pages of *page_size* user messages each.
    Up to *pages_displayed* pages are rendered at once, with navigation
    dividers between them.
    """

    _SETTINGS_KEY = "llm-thalamus"
    _SETTINGS_ORG = "llm-thalamus"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._view = QWebEngineView(self)
        self._page = _ChatPage(self._view)
        self._view.setPage(self._page)
        self._view.setZoomFactor(1.0)
        # Restore saved chat zoom.
        saved = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY).value("chat/zoom")
        if saved is not None:
            try:
                self._view.setZoomFactor(float(saved))
            except (ValueError, TypeError):
                pass
        self._view.installEventFilter(self)
        self._messages: list[dict[str, Any]] = []
        self._theme: dict[str, str] | None = None

        # ── pagination settings ──────────────────────────────────
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        self._page_size: int = self._settings_int(s, "renderer/page_size", 10)
        self._pages_displayed: int = self._settings_int(s, "renderer/pages_displayed", 2)
        self._auto_expand_thinking: int = self._settings_int(s, "renderer/auto_expand_thinking", 0)
        # The anchor page — the last (most recent) page visible.
        # Always follows the latest page during streaming.
        self._display_end_page: int = 0

        # Streaming state (UI is turn-locked, so only one assistant stream can be active).
        self._assistant_stream_active: bool = False
        self._assistant_stream_index: int | None = None

        # Thinking streaming state — independent of assistant streaming.
        self._thinking_stream_active: bool = False
        self._thinking_stream_index: int | None = None

        # When True, the next full render will scroll to bottom on page load.
        self._scroll_to_bottom: bool = True

        # When set, the next page load will scroll to this element id.
        self._toggle_scroll_target: str | None = None

        # If deltas arrive before the page finishes loading, buffer them.
        self._page_loaded: bool = False
        self._pending_assistant_deltas: list[str] = []
        self._pending_thinking_deltas: list[str] = []

        self._view.loadFinished.connect(self._on_load_finished)
        self._page.toolStackToggleRequested.connect(self._on_tool_stack_toggle_requested)
        self._page.toolStackItemToggleRequested.connect(self._on_tool_stack_item_toggle_requested)
        self._page.thinkingToggleRequested.connect(self._on_thinking_toggle)
        self._page.copyRequested.connect(self._on_copy_requested)
        self._page.navigatePageRequested.connect(self._on_navigate_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._batch_mode: bool = False
        self._render_pending: bool = False
        self._render()

    @staticmethod
    def _settings_int(s: QSettings, key: str, default: int) -> int:
        val = s.value(key)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    # ── Configuration ─────────────────────────────────────────

    def configure(
        self,
        page_size: int | None = None,
        pages_displayed: int | None = None,
        auto_expand_thinking: int | None = None,
    ) -> None:
        """Update pagination settings and persist to QSettings."""
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        if page_size is not None and page_size > 0:
            self._page_size = page_size
            s.setValue("renderer/page_size", page_size)
        if pages_displayed is not None and pages_displayed > 0:
            self._pages_displayed = pages_displayed
            s.setValue("renderer/pages_displayed", pages_displayed)
        if auto_expand_thinking is not None and auto_expand_thinking >= 0:
            self._auto_expand_thinking = auto_expand_thinking
            s.setValue("renderer/auto_expand_thinking", auto_expand_thinking)
        s.sync()
        self._render()

    def begin_batch(self) -> None:
        self._batch_mode = True

    def end_batch(self) -> None:
        self._batch_mode = False
        self._display_end_page = self._current_page_index()
        self._render()

    def _exec_js(self, js: str) -> None:
        self._view.page().runJavaScript(js)

    def _request_render(self) -> None:
        if self._render_pending:
            return
        self._render_pending = True
        QTimer.singleShot(0, self._do_deferred_render)

    def _do_deferred_render(self) -> None:
        self._render_pending = False
        self._render()

    # ── Page helpers ──────────────────────────────────────────

    def _user_message_indices(self) -> list[int]:
        """Return indices into _messages where kind=turn, role=human."""
        return [
            i
            for i, m in enumerate(self._messages)
            if isinstance(m, dict)
            and m.get("kind") == "turn"
            and m.get("role") == "human"
        ]

    def _current_page_index(self) -> int:
        """Return the 0-based page index containing the latest user message."""
        user_idx = self._user_message_indices()
        if not user_idx:
            return 0
        return (len(user_idx) - 1) // self._page_size

    def _total_pages(self) -> int:
        """Return total number of pages (at least 1)."""
        user_idx = self._user_message_indices()
        if not user_idx:
            return 1
        return max(1, (len(user_idx) + self._page_size - 1) // self._page_size)

    def _page_message_range(self, page_index: int) -> tuple[int, int] | None:
        """Return (start, end) indices into _messages for *page_index*, or None."""
        user_idx = self._user_message_indices()
        total = len(user_idx)
        if total == 0:
            if page_index == 0:
                return (0, 0)
            return None

        start_user = page_index * self._page_size
        if start_user >= total:
            return None

        end_user = min(start_user + self._page_size, total)

        start = user_idx[start_user]
        if end_user < total:
            end = user_idx[end_user]
        else:
            end = len(self._messages)

        return (start, end)

    def _visible_page_indices(self) -> list[int]:
        """Return the list of page indices currently visible."""
        total = self._total_pages()
        start = max(0, self._display_end_page - self._pages_displayed + 1)
        end = min(total, self._display_end_page + 1)
        return list(range(start, end))

    # ── Public API ────────────────────────────────────────────

    def add_turn(self, role: str, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "turn", "role": role, "content": text}
        if meta:
            msg["meta"] = meta

        # Detect page boundary crossing by counting user messages before append.
        old_page = self._current_page_index()
        self._messages.append(msg)
        new_page = self._current_page_index()

        # Any explicit add_turn finalizes any in-progress assistant stream.
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._pending_assistant_deltas.clear()

        if self._batch_mode:
            return

        if role == "human":
            if new_page != old_page:
                # Track the newest page.
                self._display_end_page = new_page
                self._render()
            else:
                self._exec_js(
                    "_appendUserBubble(" + json.dumps(escape(text)) + ")"
                )
        else:
            self._render()

    def add_activity(self, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "activity", "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)
        self._render()

    def add_steer_message(self, text: str) -> None:
        """Add a user turn during steering without touching assistant streaming."""
        msg: dict[str, Any] = {"kind": "turn", "role": "human", "content": text}
        self._messages.append(msg)
        self._exec_js(
            "_appendUserBubble(" + json.dumps(escape(text)) + ")"
        )

    # --- Thinking bubble API ---------------------------------------------------

    def add_thinking(self, text: str | None = None) -> None:
        msg: dict[str, Any] = {
            "kind": "thinking",
            "text": text or "",
            "expanded": text is None,  # expanded during live, collapsed for history
        }
        self._messages.append(msg)

        if text is None:
            self._thinking_stream_active = True
            self._thinking_stream_index = len(self._messages) - 1
            # Ensure agent work group exists via JS, then append a thinking card.
            self._exec_js(
                "(function(){"
                "var g=_ensureAgentWorkGroup();"
                "if(!g)return;"
                "var items=g.querySelector('.agent-work-items');"
                "if(!items)return;"
                "var card='<div class=\"thinking-row\" id=\"thinking-' + "
                + json.dumps(str(self._thinking_stream_index)) + " + '\">' +"
                "'  <div class=\"thinking-card\">' +"
                "'    <div class=\"thinking-header\">' +"
                "'      <div class=\"thinking-label\">💭 Thinking</div>' +"
                "'      <a class=\"thinking-toggle\" href=\"thalamus://toggle-thinking/' + "
                + json.dumps(str(self._thinking_stream_index)) + " + '\">Hide</a>' +"
                "'    </div>' +"
                "'    <div class=\"thinking-content\" id=\"thinking-stream-content-' + "
                + json.dumps(str(self._thinking_stream_index)) + " + '\"></div>' +"
                "'  </div></div>';"
                "items.insertAdjacentHTML('beforeend',card);"
                "_updateWorkGroupCount(g);"
                "})()"
            )
        else:
            self._thinking_stream_active = False
            self._thinking_stream_index = None
            self._request_render()

    def append_thinking_delta(self, text: str) -> None:
        if not self._thinking_stream_active:
            return
        if self._thinking_stream_index is None:
            return
        if not text:
            return

        self._messages[self._thinking_stream_index]["text"] += text

        if not self._page_loaded:
            self._pending_thinking_deltas.append(text)
            return

        self._append_thinking_delta_js(text)

    def end_thinking(self) -> None:
        if self._pending_thinking_deltas:
            if self._page_loaded:
                for d in self._pending_thinking_deltas:
                    self._append_thinking_delta_js(d)
            self._pending_thinking_deltas.clear()

        idx = self._thinking_stream_index
        if idx is not None:
            self._messages[idx]["expanded"] = False

        self._thinking_stream_active = False
        self._thinking_stream_index = None
        if self._page_loaded and idx is not None:
            self._exec_js(
                "(function(){"
                "var el=document.getElementById('thinking-stream-content-'"
                "+JSON.stringify(" + json.dumps(str(idx)) + "));"
                "if(!el)return;"
                "var row=el.closest('.thinking-row');"
                "if(row){var card=row.querySelector('.thinking-card');"
                "if(card){var content=card.querySelector('.thinking-content');"
                "if(content){content.style.display='none';}}}"
                "})()"
            )

    # ---------------------------------------------------------------------------

    def upsert_tool_event(self, stack_id: str, event: dict[str, Any]) -> None:
        stack = self._ensure_tool_stack(stack_id)
        event_type = str(event.get("event_type") or "")
        tool_call_id = str(event.get("tool_call_id") or "")
        item = self._ensure_tool_stack_item(
            stack,
            tool_call_id=tool_call_id,
            request_id="",
            event_type=event_type,
            event=event,
        )

        if event_type == "tool_call":
            existing_status = str(item.get("status") or "")
            tool_name = str(event.get("tool_name") or item.get("tool_name") or "tool")
            item.update(
                {
                    "tool_name": tool_name,
                    "tool_kind": event.get("tool_kind"),
                    "mcp_server_id": event.get("mcp_server_id"),
                    "mcp_remote_name": event.get("mcp_remote_name"),
                    "step": event.get("step"),
                    "args": event.get("args"),
                }
            )
            args_val = event.get("args")
            if isinstance(args_val, dict):
                item["_fmt_args"] = _format_json_block(args_val)
            if existing_status != "pending_approval":
                item["status"] = "running"
            item.pop("_partial_text", None)
            item.pop("_fmt_stream", None)
            self._exec_js(
                "_appendToolCard(" + json.dumps(stack_id) + "," + json.dumps(tool_name) + ")"
            )
        elif event_type == "tool_update":
            partial = event.get("partial_result", "")
            if partial and partial != item.get("_partial_text"):
                item["_partial_text"] = partial
                item["_fmt_stream"] = escape(partial)
                item["status"] = "running"
                self._exec_js(
                    "_appendToolText(" + json.dumps(stack_id) + "," + json.dumps(partial) + ")"
                )
        elif event_type == "tool_result":
            result = event.get("result")
            status = "ok" if bool(event.get("ok", False)) else "error"
            if isinstance(result, dict):
                error = result.get("error")
                if isinstance(error, dict) and str(error.get("code") or "") == "tool_denied":
                    status = "denied"
            item.update(
                {
                    "tool_name": str(event.get("tool_name") or item.get("tool_name") or "tool"),
                    "tool_kind": event.get("tool_kind"),
                    "mcp_server_id": event.get("mcp_server_id"),
                    "mcp_remote_name": event.get("mcp_remote_name"),
                    "step": event.get("step"),
                    "result": result,
                    "error": event.get("error"),
                    "status": status,
                }
            )
            result_text = ""
            if result is not None:
                formatted = _format_json_block(result)
                item["_fmt_result"] = formatted
                result_text = escape(formatted)
            item.pop("_partial_text", None)
            item.pop("_fmt_stream", None)
            details = event.get("details")
            if isinstance(details, dict):
                item["_fmt_details"] = _format_subagent_details(details)
            self._exec_js(
                "_finalizeToolCard(" + json.dumps(stack_id) + "," + json.dumps(result_text if result_text else "") + "," + json.dumps(status != "ok") + ")"
            )

    # --- Streaming assistant API ---

    def begin_assistant_stream(self) -> None:
        msg: dict[str, Any] = {"kind": "turn", "role": "you", "content": ""}
        self._messages.append(msg)
        self._assistant_stream_active = True
        self._assistant_stream_index = len(self._messages) - 1
        self._pending_assistant_deltas.clear()

        self._page_loaded = True
        self._exec_js("_beginAssistantBubble()")

    def append_assistant_delta(self, text: str) -> None:
        if not self._assistant_stream_active:
            return
        if self._assistant_stream_index is None:
            return
        if not text:
            return

        self._messages[self._assistant_stream_index]["content"] += text

        if not self._page_loaded:
            self._pending_assistant_deltas.append(text)
            return

        self._append_stream_delta_js(text)

    def end_assistant_stream(self) -> None:
        if self._pending_assistant_deltas:
            if self._page_loaded:
                for d in self._pending_assistant_deltas:
                    self._append_stream_delta_js(d)
            self._pending_assistant_deltas.clear()

        self._assistant_stream_active = False
        self._assistant_stream_index = None

        # Full render to apply markdown, highlighting, katex.
        self._render()

    # ---------------------------------------------------------------------------

    def set_theme(self, theme: dict[str, str] | None) -> None:
        self._theme = theme
        self._render()

    def clear(self) -> None:
        self._messages.clear()
        self._display_end_page = 0
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._thinking_stream_active = False
        self._thinking_stream_index = None
        self._pending_assistant_deltas.clear()
        self._pending_thinking_deltas.clear()
        self._render()

    # ── zoom (Ctrl + mousewheel) ────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._view and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                factor = self._view.zoomFactor()
                delta = event.angleDelta().y()
                factor = min(3.0, max(0.3, factor + (0.1 if delta > 0 else -0.1)))
                self._view.setZoomFactor(factor)
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        self.persist_zoom()
        super().closeEvent(event)

    def persist_zoom(self) -> None:
        factor = self._view.zoomFactor()
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        s.setValue("chat/zoom", factor)
        s.sync()

    # ---------------------------------------------------------------------------

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = bool(ok)

        if not self._page_loaded:
            return

        if self._assistant_stream_active and self._assistant_stream_index is not None:
            if self._pending_assistant_deltas:
                for d in self._pending_assistant_deltas:
                    self._append_stream_delta_js(d)
                self._pending_assistant_deltas.clear()
        else:
            self._pending_assistant_deltas.clear()

        if self._thinking_stream_active and self._thinking_stream_index is not None:
            if self._pending_thinking_deltas:
                for d in self._pending_thinking_deltas:
                    self._append_thinking_delta_js(d)
                self._pending_thinking_deltas.clear()
        else:
            self._pending_thinking_deltas.clear()

        self._view.page().runJavaScript("enhanceCodeBlocks()")
        self._view.page().runJavaScript("enhanceAgentWorkGroups()")

        if self._toggle_scroll_target:
            target = self._toggle_scroll_target
            self._toggle_scroll_target = None
            self._view.page().runJavaScript(
                f"var el=document.getElementById('{target}');"
                "if(el)el.scrollIntoView({behavior:'instant',block:'center'});"
            )

    def _append_stream_delta_js(self, text: str) -> None:
        js = (
            "window.thalamusAppendAssistantDelta("
            + json.dumps("assistant-stream-content") + ","
            + json.dumps(text)
            + ");"
        )
        self._view.page().runJavaScript(js)

    def _find_tool_stack(self, stack_id: str) -> dict[str, Any] | None:
        for msg in self._messages:
            if (
                isinstance(msg, dict)
                and str(msg.get("kind") or "") == "tool_stack"
                and str(msg.get("stack_id") or "") == stack_id
            ):
                return msg
        return None

    def _ensure_tool_stack(self, stack_id: str) -> dict[str, Any]:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            stack = {
                "kind": "tool_stack",
                "stack_id": stack_id,
                "expanded": False,
                "items": [],
            }
            self._messages.append(stack)
        return stack

    def _ensure_tool_stack_item(
        self,
        stack: dict[str, Any],
        *,
        tool_call_id: str,
        request_id: str,
        event_type: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        items = stack.setdefault("items", [])
        if not isinstance(items, list):
            items = []
            stack["items"] = items

        if request_id:
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                if str(item.get("request_id") or "") != request_id:
                    continue
                item.setdefault("stack_id", str(stack.get("stack_id") or ""))
                return item

        if tool_call_id:
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                if str(item.get("tool_call_id") or "") != tool_call_id:
                    continue
                existing_request_id = str(item.get("request_id") or "")
                existing_status = str(item.get("status") or "")
                if request_id and existing_request_id and existing_request_id != request_id:
                    continue
                if not request_id and event_type == "tool_call" and existing_status in {"ok", "error", "denied"}:
                    continue
                item.setdefault("stack_id", str(stack.get("stack_id") or ""))
                return item
        item = {
            "tool_call_id": tool_call_id,
            "request_id": request_id,
            "tool_name": str(event.get("tool_name") or "tool"),
            "stack_id": str(stack.get("stack_id") or ""),
            "item_key": str(tool_call_id or request_id or len(items)),
            "expanded": False,
        }
        items.append(item)
        return item

    def _on_navigate_page(self, page_index: int) -> None:
        """Navigate to a specific page (0-indexed)."""
        total = self._total_pages()
        if 0 <= page_index < total:
            self._display_end_page = page_index
            self._scroll_to_bottom = True
            self._render()

    # ── Toggle handlers (DOM-only, preserve scroll) ───────────

    def _on_tool_stack_toggle_requested(self, stack_id: str) -> None:
        """Toggle tool-stack expand/collapse via JS DOM — no full render."""
        self._exec_js(
            "(function(){"
            "var savedY=_saveScrollY();"
            "var row=document.getElementById(" + json.dumps(f"tool-stack-{stack_id}") + ");"
            "if(!row)return;"
            "var items=row.querySelector('.tool-stack-items');"
            "if(!items)return;"
            "var toggle=row.querySelector('.thinking-toggle');"
            "var wasHidden=items.style.display==='none';"
            "if(wasHidden){"
            "items.style.display='';"
            "if(toggle)toggle.textContent='Hide';"
            "}else{"
            "items.style.display='none';"
            "if(toggle)toggle.textContent='Show';"
            "}"
            "_restoreScrollY(savedY);"
            "})()"
        )

    def _on_tool_stack_item_toggle_requested(self, stack_id: str, item_key: str) -> None:
        """Toggle individual tool-stack item body via JS DOM — no full render."""
        self._exec_js(
            "(function(){"
            "var savedY=_saveScrollY();"
            "var row=document.getElementById(" + json.dumps(f"tool-stack-{stack_id}") + ");"
            "if(!row)return;"
            "var items=row.querySelector('.tool-stack-items');"
            "if(!items)return;"
            "var children=items.children;"
            "var found=false;"
            "for(var i=0;i<children.length;i++){"
            "var itemKey=children[i].getAttribute('data-item-key');"
            "if(itemKey!==" + json.dumps(item_key) + ")continue;"
            "var bodyDiv=children[i].querySelector('.tool-stack-item-body');"
            "if(bodyDiv){"
            "var wasHidden=bodyDiv.style.display==='none';"
            "bodyDiv.style.display=wasHidden?'':'none';"
            "}"
            "found=true;break;"
            "}"
            "if(!found)return;"
            "_restoreScrollY(savedY);"
            "})()"
        )

    def _on_thinking_toggle(self, index: int) -> None:
        """Toggle thinking bubble expand/collapse via JS DOM — no full render."""
        self._exec_js(
            "(function(){"
            "var savedY=_saveScrollY();"
            "var row=document.getElementById(" + json.dumps(f"thinking-{index}") + ");"
            "if(!row)return;"
            "var content=row.querySelector('.thinking-content');"
            "if(!content)return;"
            "var toggle=row.querySelector('.thinking-toggle');"
            "var wasHidden=content.style.display==='none';"
            "if(wasHidden){"
            "content.style.display='';"
            "if(toggle)toggle.textContent='Hide';"
            "}else{"
            "content.style.display='none';"
            "if(toggle)toggle.textContent='Show';"
            "}"
            "_restoreScrollY(savedY);"
            "})()"
        )

    def _on_copy_requested(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def _append_thinking_delta_js(self, text: str) -> None:
        if self._thinking_stream_index is None:
            return
        target_id = f"thinking-stream-content-{self._thinking_stream_index}"
        js = (
            "window.thalamusAppendThinkingDelta("
            + json.dumps(target_id) + ","
            + json.dumps(text)
            + ");"
        )
        self._view.page().runJavaScript(js)

    def _render(self) -> None:
        if self._batch_mode:
            return

        self._page_loaded = False

        # Always follow the latest page during streaming or after new content.
        if self._assistant_stream_active or self._thinking_stream_active:
            self._display_end_page = self._current_page_index()

        visible_pages = self._visible_page_indices()
        total_pages = self._total_pages()

        # Build page HTML slices.
        page_htmls: list[str] = []
        for pi in visible_pages:
            prange = self._page_message_range(pi)
            if prange is None:
                continue
            s, e = prange
            page_htmls.append(
                _messages_to_html(
                    self._messages,
                    assistant_stream_index=self._assistant_stream_index
                    if self._assistant_stream_active
                    else None,
                    thinking_stream_index=self._thinking_stream_index
                    if self._thinking_stream_active
                    else None,
                    page_start=s,
                    page_end=e,
                )
            )

        # Build the navigation dividers.
        all_parts: list[str] = []
        # Top divider (always shown when there are pages rendered).
        all_parts.append(
            _page_nav_html(visible_pages[0], visible_pages[-1], total_pages)
        )
        # Page content + between dividers.
        for idx, ph in enumerate(page_htmls):
            all_parts.append(ph)
            if idx < len(page_htmls) - 1:
                all_parts.append(
                    _page_nav_html(visible_pages[0], visible_pages[-1], total_pages)
                )
        # Bottom divider.
        all_parts.append(
            _page_nav_html(visible_pages[0], visible_pages[-1], total_pages)
        )

        messages_html = "\n".join(all_parts)
        html = _build_html_document(
            messages_html, theme=self._theme, scroll_to_bottom=self._scroll_to_bottom
        )
        self._scroll_to_bottom = True
        self._view.setHtml(html, QUrl("file:///"))
