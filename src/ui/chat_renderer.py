#!/usr/bin/env python3
"""ChatRenderer — a paginated QWebEngineView chat bubble renderer.

Architecture
────────────
Two-layer design:

  1. Pure functions        — ``messages_to_html()`` and module-level helpers.
     No Qt imports, no side effects.  Convert a slice of ``_messages[]``
     into inner HTML.

  2. ChatRenderer(QWidget) — thin wrapper around QWebEngineView.  Owns
     ``_messages[]``, manages the render cycle, and bridges HTML ↔ Python
     via ``thalamus://`` URLs.  Configuration is stored in memory; QSettings
     persistence belongs to main_window.py.

Data model
──────────
``_messages`` is a list of dicts.  Each dict has a ``kind`` field:

  - ``kind="turn"``          — user or assistant speech bubble (markdown-formatted)
  - ``kind="thinking"``       — reasoning text (rendered as raw text between turns)
  - ``kind="tool_stack"``     — tool execution (rendered as raw text between turns)
  - ``kind="activity"``       — legacy activity message
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from markdown_it import MarkdownIt
from mdit_py_plugins.amsmath import amsmath_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.texmath import texmath_plugin


# ═══════════════════════════════════════════════════════════════════
#  Markdown parser — single shared instance
# ═══════════════════════════════════════════════════════════════════

_md = (
    MarkdownIt("commonmark", {"html": True})
    .enable("table")
    .use(dollarmath_plugin)
    .use(texmath_plugin, delimiters="brackets")
    .use(amsmath_plugin)
)


# ═══════════════════════════════════════════════════════════════════
#  Module-level helpers (pure functions, no Qt)
# ═══════════════════════════════════════════════════════════════════


def _split_out_code_fences(markdown: str) -> list[str]:
    """Split markdown into segments, preserving fenced code blocks."""
    parts: list[str] = []
    fence = re.compile(r"```(.*?)```", re.DOTALL)
    last = 0
    for m in fence.finditer(markdown):
        if m.start() > last:
            parts.append(markdown[last : m.start()])
        parts.append(markdown[m.start() : m.end()])
        last = m.end()
    if last < len(markdown):
        parts.append(markdown[last:])
    return parts


def _render_file_references(content: str) -> str:
    """Replace ``[file: /path/to/file.ext]`` with native markdown.

    - Images: ``![](/absolute/path)`` — the markdown parser
      handles loading the file via QtWebEngine's local file access.
    - Audio:  ``<audio controls src="/absolute/path">`` — inline player.
    - Other:  left as-is.

    Paths are URL-encoded to handle spaces and special characters.

    Content inside inline code spans (``...``) and fenced code blocks
    (```...```) is preserved as-is so that quoted or backtick-escaped
    references are never accidentally expanded.
    """
    from urllib.parse import quote as _url_quote
    _NONCE = "\x00FILEREF_SKIP_"
    protected: dict[str, str] = {}

    def _protect(m: re.Match) -> str:
        key = f"{_NONCE}{len(protected)}\x00"
        protected[key] = m.group(0)
        return key

    content = re.sub(r"(?s)```.*?```", _protect, content)
    content = re.sub(r"`(?:[^`]|\\`)*?`", _protect, content)

    pattern = re.compile(r"\[file: ([^\]]+)\]")

    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
    _AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm")

    def _replace(match: re.Match) -> str:
        path = match.group(1)
        ext = Path(path).suffix.lower()
        name = Path(path).name

        if ext in _IMG_EXTS:
            # Use the raw absolute path — markdown-it commonmark does
            # not parse file:/// URIs, but resolves /absolute/paths
            # correctly against the QUrl("file:///") base URL.
            return f"![{escape(name)}]({_url_quote(path, safe='/')})"

        if ext in _AUDIO_EXTS:
            return f'<audio controls src="{_url_quote(path, safe='/')}">{escape(name)}</audio>'

        return match.group(0)

    content = pattern.sub(_replace, content)

    # Handle HTML <img> and <audio> tags — URL-encode local file paths
    def _replace_html_tag(match: re.Match) -> str:
        tag = match.group(1)
        attrs = match.group(2) or ""
        src_m = re.search(r'\bsrc="([^"]+)"', attrs)
        if not src_m:
            return match.group(0)
        path = src_m.group(1)
        ext = Path(path).suffix.lower()

        if tag == "img" and ext in _IMG_EXTS:
            encoded = _url_quote(path, safe='/')
            new_attrs = attrs[:src_m.start(1)] + encoded + attrs[src_m.end(1):]
            return f'<img{new_attrs}>'

        if tag == "audio" and ext in _AUDIO_EXTS:
            encoded = _url_quote(path, safe='/')
            new_attrs = attrs[:src_m.start(1)] + encoded + attrs[src_m.end(1):]
            if "controls" not in attrs:
                new_attrs += " controls"
            return f'<audio{new_attrs}>'

        return match.group(0)

    html_tag_re = re.compile(r'<(img|audio)([^>]*)>', re.IGNORECASE)
    content = html_tag_re.sub(_replace_html_tag, content)

    for key, original in protected.items():
        content = content.replace(key, original)

    return content


def format_content_to_html(content: str) -> str:
    """Render markdown → HTML with fenced-code highlighting placeholders.

    Before markdown rendering, ``[file: /path]`` references are replaced
    with inline media (images, audio players).
    """
    content = _render_file_references(content)

    segments = _split_out_code_fences(content)
    out: list[str] = []
    fence_re = re.compile(r"^```(\w+)?\n(.*)\n```$", re.DOTALL)

    for seg in segments:
        seg = seg or ""
        m = fence_re.match(seg.strip())
        if m:
            lang = (m.group(1) or "").strip().lower()
            code = m.group(2) or ""
            lang_class = f" language-{lang}" if lang else ""
            out.append(
                f'<pre class="code-block"><code class="{lang_class}">'
                f"{escape(code)}"
                f"</code></pre>"
            )
        else:
            out.append(_md.render(seg))

    return "".join(out)


def _format_json_block(value: Any) -> str:
    """Format a Python value for display in a ``<pre>``."""
    try:
        if isinstance(value, str):
            return escape(value)
        formatted = json.dumps(value, ensure_ascii=False, indent=2)
        formatted = formatted.replace("\\n", "\n").replace("\\t", "\t")
        return escape(formatted)
    except Exception:
        return escape(str(value))


def _fmt_tokens(count: int) -> str:
    """Format a token count with k / M suffix."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)


def _format_subagent_details(details: dict) -> str:
    """Format subagent result details into compact HTML."""
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
    return " &middot; ".join(parts)


def _summary_from_args(tool_name: str, args: dict[str, Any]) -> str:
    """Extract a human-readable preview from structured tool arguments."""
    primary_field: dict[str, str] = {
        "bash": "command",
        "read": "path",
        "write": "path",
        "grep": "pattern",
        "find": "path",
        "ls": "path",
        "subagent": "task",
        "mempalace_search": "query",
        "mempalace_remember": "summary",
        "mempalace_diary_read": "agent_name",
        "mempalace_diary_write": "agent_name",
        "mempalace_open_loops": "query",
        "mempalace_get_drawer": "drawer_id",
        "mempalace_list_drawers": "wing",
        "mempalace_mine_project": "path",
        "mempalace_wake_up": "wing",
        "fetch_url": "url",
        "recall": "id",
        "intercom": "action",
    }

    field = primary_field.get(tool_name)
    if field:
        val = args.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # edit: show path + brief oldText snippet.
    if tool_name == "edit" and isinstance(args.get("path"), str):
        path = args["path"]
        old = args.get("oldText")
        if isinstance(old, str) and len(old) < 60:
            return f"{path} ← {old}"
        return path

    # Generic: first string value.
    for v in args.values():
        if isinstance(v, str) and v.strip():
            return v.strip()[:180]
        if isinstance(v, (int, float)):
            return str(v)[:180]

    return ""


def _decode_html_entities(text: str) -> str:
    """Decode common HTML entities back to plain text."""
    return (
        text.replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )


# ═══════════════════════════════════════════════════════════════════
#  CSS
# ═══════════════════════════════════════════════════════════════════

_PAGE_NAV_CSS = """
.page-divider {
    display: flex; align-items: center; gap: 12px; margin: 16px 0;
}
.page-divider::before, .page-divider::after {
    content: ''; flex: 1; border-top: 2px dashed var(--border);
}
.page-nav-prev, .page-nav-next {
    color: var(--meta-text); text-decoration: none; font-size: 13px;
    font-weight: 600; padding: 2px 8px;
}
.page-nav-prev:hover, .page-nav-next:hover {
    color: var(--text); text-decoration: underline;
}
.page-nav-label {
    font-size: 13px; color: var(--meta-text); white-space: nowrap;
}
.page-nav-goto {
    width: 3em; font-size: 13px; text-align: center;
    border: 1px solid var(--border); border-radius: 4px; padding: 1px 4px;
}
"""
_STYLE_CSS = r"""
:root { /* THEME_VARS */ }
body {
    margin: 0; padding: 8px; background-color: var(--bg); color: var(--text);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 16px; line-height: 1.4;
}
body[data-ready="0"] { visibility: hidden; }
.chat-container { margin: 0 auto; }

/* Message rows */
.message-row { display: flex; margin: 6px 0; }
.message-row.user { justify-content: flex-start; }
.message-row.assistant { justify-content: flex-end; }
.message-row.agent-work { justify-content: flex-end; }

/* Bubbles */
.bubble {
    position: relative;
    border-radius: 14px; padding: 8px 12px; max-width: 88%;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08); font-size: 16px;
    line-height: 1.4; word-wrap: break-word; white-space: normal;
}
.bubble.user { background: var(--bubble-user); color: var(--text); }
.bubble.assistant { background: var(--bubble-assistant); color: var(--text); }
.bubble.latest {
    box-shadow: 0 0 0 3px var(--border), 0 0 8px rgba(0,0,0,0.35);
}
.bubble img { max-width: 100%; height: auto; border-radius: 8px; }

.bubble.agent-work {
    background: rgba(240,240,244,0.5); border: 1px solid var(--border);
    max-width: 88%; width: 100%; font-size: 13px; line-height: 1.4;
    white-space: pre-wrap; word-break: break-word;
    font-family: "Fira Code", "JetBrains Mono", monospace;
}
.agent-work-title {
    font-size: 11px; color: var(--meta-text); opacity: 0.6;
    margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;
    cursor: pointer; user-select: none;
}
.agent-work-title:hover { opacity: 1.0; }
.agent-work-title::before { content: "\25BC"; font-size: 8px; margin-right: 4px; display: inline-block; }
.agent-work-collapsed .agent-work-title::before { content: "\25B6"; }
.agent-work-collapsed .agent-work-content { display: none; }
.aw-thinking {
    background: rgba(220,230,255,0.25); border-radius: 8px;
    padding: 4px 8px; margin: 2px 0;
}
.aw-thinking-title {
    font-size: 10px; color: var(--meta-text); opacity: 0.5;
    cursor: pointer; user-select: none; margin-bottom: 2px;
    text-transform: uppercase; letter-spacing: 0.3px;
}
.aw-thinking-title:hover { opacity: 0.8; }
.aw-thinking-title::before { content: "\25BC"; font-size: 7px; margin-right: 3px; display: inline-block; }
.aw-thinking-collapsed .aw-thinking-title::before { content: "\25B6"; }
.aw-thinking-collapsed .aw-thinking-body { display: none; }
.aw-tool-header {
    font-size: 11px; font-weight: 600; color: var(--text);
    padding: 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: pointer; user-select: none;
}
.aw-tool-header::before { content: "\25BC"; font-size: 8px; margin-right: 4px; display: inline-block; }
.aw-tool.aw-tool-collapsed .aw-tool-header::before { content: "\25B6"; }
.aw-tool-body {
    margin-top: 2px; padding-top: 2px;
    border-top: 1px solid rgba(0,0,0,0.06);
}
.aw-tool.aw-tool-collapsed .aw-tool-body { display: none; }
.aw-tool {
    background: rgba(230,240,230,0.3); border-radius: 8px;
    padding: 4px 8px; margin: 2px 0;
    font-size: 13px; font-family: "Fira Code", "JetBrains Mono", monospace;
}
.aw-tool-nested {
    margin-left: 1.25em; margin-top: 4px; margin-bottom: 4px;
    padding: 2px 6px;
}
.aw-tool-nested .aw-tool-body {
    font-size: 12px; margin-top: 1px; padding-top: 1px;
}
.aw-tool-subagent {
    background: rgba(200,220,250,0.3);
}
.meta { font-size: 11px; color: var(--meta-text); margin-bottom: 2px; }

/* Code blocks */
pre.code-block {
    background: #1e1e1e; color: #f5f5f5; padding: 8px 10px;
    border-radius: 8px; font-family: "Fira Code","JetBrains Mono",monospace;
    font-size: 16px; overflow-x: auto; white-space: pre; margin: 4px 0;
    position: relative; padding-top: 26px;
}
pre.code-block code { white-space: pre; }
.copy-code-btn, .bubble-copy-btn {
    position: absolute; top: 4px; right: 6px; font-size: 11px;
    padding: 2px 8px; border-radius: 4px; border: 1px solid #555;
    background: #2b2b2b; color: #f5f5f5; cursor: pointer; opacity: 0.8;
}
.copy-code-btn:hover, .bubble-copy-btn:hover { opacity: 1.0; }
.copy-code-btn:active, .bubble-copy-btn:active { transform: translateY(1px); }

.bubble-copy-btn { background: transparent; color: #000; }

/* Images, tables, math */
table { border-collapse: collapse; margin: 6px 0; font-size: 12px; width: 100%;
    display: block; overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 4px 8px; text-align: left;
    vertical-align: top; }
th { background: rgba(0,0,0,0.04); font-weight: 600; }
tr:nth-child(even) { background: rgba(0,0,0,0.02); }
eq, eqn, .math.amsmath { display: inline; }
eqn, .math.amsmath { display: block; margin: 6px 0; }

/* Scrollbar */
body::-webkit-scrollbar { width: 10px; }
body::-webkit-scrollbar-track { background: var(--bg); }
body::-webkit-scrollbar-thumb { background-color: var(--border);
    border-radius: 5px; border: 2px solid var(--bg); }
"""


# ═══════════════════════════════════════════════════════════════════
#  JavaScript runtime (inline in HTML)
# ═══════════════════════════════════════════════════════════════════

_JS_RUNTIME = r"""
function _isAtBottom(tolerancePx) {
    var tol = (typeof tolerancePx === "number") ? tolerancePx : 6;
    var el = document.documentElement;
    return (window.innerHeight + window.scrollY) >= (el.scrollHeight - tol);
}
function _scrollToBottom() {
    window.scrollTo(0, document.documentElement.scrollHeight);
}

function prettifyJsonBlocks() {
    document.querySelectorAll('pre.code-block code.language-json').forEach(function(block) {
        try {
            var text = block.textContent, trimmed = text.trim();
            if (!trimmed) return;
            var obj = JSON.parse(trimmed);
            var pretty = JSON.stringify(obj, null, 2);
            if (pretty !== text) block.textContent = pretty;
        } catch(e) {}
    });
}

function highlightCodeBlocks() {
    if (typeof hljs === "undefined") return;
    document.querySelectorAll('pre.code-block > code').forEach(function(block) {
        hljs.highlightElement(block);
    });
}

function enhanceCodeBlocks() {
    document.querySelectorAll('pre.code-block').forEach(function(pre) {
        if (pre.querySelector('.copy-code-btn')) return;
        var button = document.createElement('button');
        button.type = 'button'; button.className = 'copy-code-btn';
        button.textContent = 'Copy';
        button.addEventListener('click', function(ev) {
            ev.stopPropagation();
            var code = pre.querySelector('code');
            var text = code ? code.textContent : pre.textContent;
            var old = button.textContent;
            button.textContent = 'Copied!';
            setTimeout(function() { button.textContent = old; }, 1200);
            location.href = 'thalamus://copy/' + encodeURIComponent(text);
        });
        pre.appendChild(button);
    });
}

function addBubbleCopyButtons() {
    document.querySelectorAll('.bubble').forEach(function(bubble) {
        if (bubble.querySelector('.bubble-copy-btn')) return;
        var btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'bubble-copy-btn';
        btn.textContent = 'Copy';
        btn.addEventListener('click', function(ev) {
            ev.stopPropagation();
            var text = '';
            for (var i = 0; i < bubble.childNodes.length; i++) {
                var n = bubble.childNodes[i];
                if (n.nodeType === 3) text += n.textContent;
                else if (n.nodeType === 1 && !n.classList.contains('bubble-copy-btn'))
                    text += n.textContent;
            }
            text = text.trim();
            var old = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = old; }, 1200);
            location.href = 'thalamus://copy/' + encodeURIComponent(text);
        });
        bubble.appendChild(btn);
    });
}

function renderMathNodes() {
    if (typeof katex === "undefined" || !katex.render) return;
    function renderNode(el, displayMode) {
        if (!el) return;
        var tex = el.textContent || "";
        el.innerHTML = "";
        try { katex.render(tex, el, { displayMode: displayMode, throwOnError: false }); }
        catch(e) { el.textContent = tex; }
    }
    Array.from(document.getElementsByTagName("eq")).forEach(function(el) { renderNode(el, false); });
    Array.from(document.getElementsByTagName("eqn")).forEach(function(el) { renderNode(el, true); });
    document.querySelectorAll("div.math.amsmath").forEach(function(el) { renderNode(el, true); });
}

/* ── Streaming helpers ─────────────────────────────────────── */

window.thalamusAppendAssistantDelta = function(targetId, deltaText) {
    try {
        var atBottom = _isAtBottom(8);
        var el = document.getElementById(targetId);
        if (!el) return false;
        el.appendChild(document.createTextNode(deltaText));
        if (atBottom) setTimeout(function() { _scrollToBottom(); }, 0);
        return true;
    } catch(e) { return false; }
};

window._appendMessage = function(html) {
    try {
        var atBottom = _isAtBottom(8);
        var container = document.querySelector('.chat-container');
        if (!container) return false;
        container.insertAdjacentHTML('beforeend', html);
        if (atBottom) setTimeout(function() { _scrollToBottom(); }, 0);
        return true;
    } catch(e) { return false; }
};

window._appendUserBubble = function(text) {
    var r = _appendMessage(
        '<div class="message-row user"><div class="bubble user">' + text + '</div></div>');
    addBubbleCopyButtons();
    return r;
};

window._beginAssistantBubble = function() {
    try {
        var atBottom = _isAtBottom(8);
        var html = '<div class="message-row assistant">' +
            '<div class="bubble assistant latest">' +
            '<div id="assistant-stream-content" style="white-space: pre-wrap;"></div>' +
            '</div></div>';
        var container = document.querySelector('.chat-container');
        if (!container) return false;
        container.insertAdjacentHTML('beforeend', html);
        addBubbleCopyButtons();
        if (atBottom) setTimeout(function() { _scrollToBottom(); }, 0);
        var prevAssistant = container.querySelectorAll('.bubble.assistant.latest');
        for (var i = 0; i < prevAssistant.length - 1; i++)
            prevAssistant[i].classList.remove('latest');
        return true;
    } catch(e) { return false; }
};

/* Page navigation */
function _toggleAgentWork(el) {
    var row = el.closest('.message-row.agent-work');
    if (row) row.classList.toggle('agent-work-collapsed');
}
function _toggleAwThinking(el) {
    var block = el.closest('.aw-thinking');
    if (block) block.classList.toggle('aw-thinking-collapsed');
}
function _toggleAwTool(el) {
    var tool = el.closest('.aw-tool');
    if (tool) tool.classList.toggle('aw-tool-collapsed');
}

function _handleGoToPage(inputEl, totalPages) {
    var val = parseInt(inputEl.value, 10);
    if (isNaN(val) || val < 1) return;
    var pageIdx = Math.min(val - 1, totalPages - 1);
    location.href = 'thalamus://navigate-page/' + pageIdx;
}

/* DOM ready */
document.addEventListener("DOMContentLoaded", function() {
    prettifyJsonBlocks();
    highlightCodeBlocks();
    enhanceCodeBlocks();
    addBubbleCopyButtons();
    renderMathNodes();
    if (document.body.getAttribute("data-scroll") === "1") _scrollToBottom();
    requestAnimationFrame(function() { document.body.setAttribute("data-ready", "1"); });
});
"""


# ═══════════════════════════════════════════════════════════════════
#  HTML template
# ═══════════════════════════════════════════════════════════════════

HTML_TEMPLATE = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
{_STYLE_CSS}
/* PAGE_NAV_CSS */
</style>
<link rel="stylesheet" href="file:///usr/lib/node_modules/katex/dist/katex.min.css">
<script defer src="file:///usr/lib/node_modules/katex/dist/katex.min.js"></script>
<link rel="stylesheet"
      href="file:///usr/lib/node_modules/@highlightjs/cdn-assets/styles/github-dark.min.css">
<script src="file:///usr/lib/node_modules/@highlightjs/cdn-assets/highlight.min.js"></script>
<script>
{_JS_RUNTIME}
</script>
</head>
<body data-ready="0" data-scroll="{{scroll}}">
<div class="chat-container">
{{messages_html}}
</div>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════
#  Page navigation HTML builder
# ═══════════════════════════════════════════════════════════════════


def _page_nav_html(
    display_start: int,
    display_end: int,
    total_pages: int,
) -> str:
    """Build a page navigation bar with Prev/Next, page counter, and Go-to input."""
    has_prev = display_start > 0
    has_next = display_end < total_pages - 1
    prev_page = display_start - 1 if has_prev else -1
    next_page = display_end + 1 if has_next else -1

    prev_html = (
        f'<a class="page-nav-prev" href="thalamus://navigate-page/{prev_page}">\u25c0 Prev</a>'
        if has_prev
        else '<span class="page-nav-prev" style="visibility:hidden">\u25c0 Prev</span>'
    )
    next_html = (
        f'<a class="page-nav-next" href="thalamus://navigate-page/{next_page}">Next \u25b6</a>'
        if has_next
        else '<span class="page-nav-next" style="visibility:hidden">Next \u25b6</span>'
    )

    if display_start == display_end:
        label = f"Page {display_start + 1} / {total_pages}"
    else:
        label = f"Pages {display_start + 1}\u2013{display_end + 1} / {total_pages}"

    goto = (
        f'<input class="page-nav-goto" type="text" placeholder="Go" '
        f'onkeydown="if(event.key===\'Enter\'){{_handleGoToPage(this,{total_pages})}}" />'
    )

    return (
        f'<div class="page-divider">'
        f"{prev_html}"
        f'<span class="page-nav-label">{label}</span>'
        f"{next_html}"
        f"{goto}"
        f"</div>"
    )


# ═══════════════════════════════════════════════════════════════════
#  URL bridge page
# ═══════════════════════════════════════════════════════════════════


class _ChatPage(QWebEnginePage):
    """Intercepts ``thalamus://`` URLs to bridge HTML ↔ Python."""

    copyRequested = Signal(str)
    navigatePageRequested = Signal(int)

    def createWindow(self, _type: Any) -> _ChatPage:
        return self

    def acceptNavigationRequest(
        self, url: QUrl, nav_type: Any, is_main_frame: bool
    ) -> bool:
        # Intercept file:// link clicks — open in system default app.
        if url.scheme() == "file" and nav_type == QWebEnginePage.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False

        if url.scheme() != "thalamus":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        host = url.host()
        path = url.path().lstrip("/")

        if host == "copy":
            text = path
            if text:
                self.copyRequested.emit(text)
        elif host == "navigate-page":
            try:
                self.navigatePageRequested.emit(int(path))
            except ValueError:
                pass

        return False  # never navigate to thalamus:// URLs


# ═══════════════════════════════════════════════════════════════════
#  Rendering: raw activity bubble (collects thinking + tool text)
# ═══════════════════════════════════════════════════════════════════

_NON_TURN_KINDS = frozenset({"thinking", "tool_stack"})


def _extract_result_text(item: dict[str, Any]) -> str:
    """Extract tool result text from the best available source."""
    result = item.get("result")
    if result is not None:
        if isinstance(result, str):
            return result
        elif isinstance(result, (dict, list)):
            try:
                return json.dumps(result, indent=2)
            except Exception:
                return str(result)
        else:
            return str(result)

    # Fallback: _fmt_result (HTML-escaped, needs decoding).
    fmt_result = item.get("_fmt_result")
    if isinstance(fmt_result, str) and fmt_result.strip():
        plain = _decode_html_entities(fmt_result)
        plain = re.sub(r"<[^>]+>", "", plain).strip()
        if plain:
            return plain

    # Fallback: _fmt_stream (HTML-escaped, needs decoding).
    fmt_stream = item.get("_fmt_stream")
    if isinstance(fmt_stream, str) and fmt_stream.strip():
        plain = _decode_html_entities(fmt_stream)
        plain = re.sub(r"<[^>]+>", "", plain).strip()
        if plain:
            return plain

    return ""


def _render_raw_activity_bubble(
    msgs: list[dict[str, Any]],
    *,  # keyword-only arg
    collapsed: bool = False,
    thinking_threshold: int = 0,
    thinking_counter: list[int] | None = None,
    tools_threshold: int = 0,
    tools_counter: list[int] | None = None,
) -> str:
    """Render a list of non-turn messages (thinking, tool_stack, activity)
    as a single right-aligned raw-text bubble with a title."""
    html_parts: list[str] = []
    _item_count: int = 0

    def _add_thinking(msg):
        nonlocal _item_count
        text = str(msg.get("text") or "").strip()
        if not text:
            return
        _item_count += 1
        idx = thinking_counter[0] if thinking_counter else 0
        if thinking_counter is not None:
            thinking_counter[0] += 1
        tc = " aw-thinking-collapsed" if thinking_threshold > 0 and idx < thinking_threshold else ""
        html_parts.append(
            f'<div class="aw-thinking{tc}">'
            f'  <div class="aw-thinking-title" onclick="_toggleAwThinking(this)">Thinking</div>'
            f'  <div class="aw-thinking-body">{escape(text)}</div>'
            f'</div>'
        )

    def _add_tool_stack(msg):
        nonlocal _item_count
        items = msg.get("items", [])
        if not items:
            return
        _item_count += len([x for x in items if isinstance(x, dict)])
        for item in items:
            if not isinstance(item, dict):
                continue
            tn = str(item.get("tool_name") or "tool")
            args = item.get("args")

            # Tool collapse index (across all agent-work bubbles).
            tool_idx = tools_counter[0] if tools_counter else 0
            if tools_counter is not None:
                tools_counter[0] += 1
            tool_collapsed = tools_threshold > 0 and tool_idx < tools_threshold

            # Build the header label.
            display_name = tn[0].upper() + tn[1:] if tn else "Tool"
            if tn == "subagent":
                # For subagent, just use the agent name from args.
                agent_name = ""
                if isinstance(args, dict):
                    agent_name = str(args.get("agent") or args.get("task") or "")
                header = f"Subagent: {agent_name}" if agent_name else "Subagent"
            elif tn == "bash":
                cmd = ""
                if isinstance(args, dict):
                    cmd = str(args.get("command") or "")
                header = f"Bash: {cmd}" if cmd else "Bash"
            elif tn == "read":
                path = ""
                if isinstance(args, dict):
                    path = str(args.get("path") or "")
                header = f"Read: {path}" if path else "Read"
            elif tn == "edit":
                path = ""
                if isinstance(args, dict):
                    path = str(args.get("path") or "")
                header = f"Edit: {path}" if path else "Edit"
            elif tn == "write":
                path = ""
                if isinstance(args, dict):
                    path = str(args.get("path") or "")
                header = f"Write: {path}" if path else "Write"
            else:
                summary = _summary_from_args(tn, args) if isinstance(args, dict) else ""
                header = f"{display_name}: {summary}" if summary else display_name

            # Collect body (result text, status, errors).
            body_lines: list[str] = []
            if item.get("error"):
                body_lines.append(f"Error: {item['error']}")
            st = str(item.get("status") or "")
            if st == "running":
                body_lines.append("Status: running")
            elif st == "error":
                body_lines.append("Status: failed")
            elif st == "denied":
                body_lines.append("Status: denied")
            rt = _extract_result_text(item)
            if rt:
                body_lines.append(rt)

            # Live subagent progress during execution.
            running_progress: list[str] = []
            if tn == "subagent" and st == "running":
                running_details = item.get("_fmt_running_details")
                if isinstance(running_details, dict):
                    progress_list = running_details.get("progress", [])
                    if progress_list and isinstance(progress_list[0], dict):
                        p0 = progress_list[0]
                        ct = p0.get("currentTool")
                        cta = p0.get("currentToolArgs", "")
                        if ct:
                            running_progress.append(f"Status: running · tool: {escape(str(ct))}")
                            if cta:
                                running_progress.append(f"  Args: {escape(str(cta))}")
                        recent = p0.get("recentTools", [])
                        if recent:
                            running_progress.append("  Recent tools:")
                            for rt_item in recent[-5:]:  # last 5
                                tname = escape(str(rt_item.get("tool", "")))
                                targs = escape(str(rt_item.get("args", "")))
                                if targs and targs != "None":
                                    running_progress.append(f"    \u2192 {tname} {targs}")
                                else:
                                    running_progress.append(f"    \u2192 {tname}")
                    rlist = running_details.get("results", [])
                    if rlist and isinstance(rlist[0], dict):
                        msgs = rlist[0].get("messages", [])
                        if msgs:
                            for m in msgs:
                                if not isinstance(m, dict):
                                    continue
                                role = m.get("role", "")
                                content = m.get("content", "")
                                if role == "user" and isinstance(content, str):
                                    # Keep first user message (the prompt) brief.
                                    text = content[:200].replace("\n", " ")
                                    if len(text) == 200:
                                        text += "..."
                                    if text.strip():
                                        running_progress.append(f"Prompt: {escape(text.strip())}")
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict):
                                            btype = block.get("type", "")
                                            if btype == "thinking":
                                                ttext = escape(block.get("thinking", ""))
                                                if ttext:
                                                    running_progress.append(f"Thinking: {ttext[:200]}")
                                                    if len(ttext) > 200:
                                                        running_progress[-1] += "..."
                                            elif btype == "toolCall":
                                                tc_name = escape(str(block.get("name", "")))
                                                tc_args = block.get("args", {})
                                                if isinstance(tc_args, dict):
                                                    tc_args = escape(json.dumps(tc_args))
                                                else:
                                                    tc_args = escape(str(tc_args))
                                                if tc_name:
                                                    running_progress.append(f"  \u2192 {tc_name} {tc_args}")

            # Nested tool cards for subagent (post-completion).
            nested_html = ""
            if tn == "subagent":
                details = item.get("details")
                if isinstance(details, dict):
                    results_list = details.get("results", [])
                    if results_list and isinstance(results_list[0], dict):
                        for tc in results_list[0].get("toolCalls", []):
                            if not isinstance(tc, dict):
                                continue
                            tc_text = escape(tc.get("text", ""))
                            tc_expanded = escape(tc.get("expandedText", ""))
                            tc_idx = tools_counter[0] if tools_counter else 0
                            if tools_counter is not None:
                                tools_counter[0] += 1
                            tc_collapsed = tools_threshold > 0 and tc_idx < tools_threshold
                            tc_css = "aw-tool aw-tool-nested"
                            if tc_collapsed:
                                tc_css += " aw-tool-collapsed"
                            nested_html += f'<div class="{tc_css}">'
                            nested_html += f'  <div class="aw-tool-header" onclick="_toggleAwTool(this)">{tc_text}</div>'
                            if tc_expanded and tc_expanded != tc_text:
                                nested_html += f'  <div class="aw-tool-body">{tc_expanded}</div>'
                            nested_html += "</div>"

            body_text = "\n".join(body_lines)

            css_class = "aw-tool"
            if tn == "subagent":
                css_class += " aw-tool-subagent"
            if item.get("status") == "error":
                css_class += " aw-error"
            if tool_collapsed:
                css_class += " aw-tool-collapsed"

            html = f'<div class="{css_class}">'
            html += f'  <div class="aw-tool-header" onclick="_toggleAwTool(this)">{escape(header)}</div>'
            parts: list[str] = []
            if running_progress:
                parts.append(f'<div class="aw-tool-body">{"<br>".join(running_progress)}</div>')
            if body_text:
                parts.append(f'<div class="aw-tool-body">{escape(body_text)}</div>')
            if nested_html:
                parts.append(f'<div class="aw-tool-body">{nested_html}</div>')
            html += "".join(parts)
            html += "</div>"
            html_parts.append(html)

    def _add_activity(msg):
        nonlocal _item_count
        text = str(msg.get("content") or "").strip()
        if text:
            _item_count += 1
            html_parts.append(f'<div class="aw-thinking">{escape(text)}</div>')

    i = 0
    while i < len(msgs):
        msg = msgs[i]
        kind = msg.get("kind")
        if kind == "thinking" and i + 1 < len(msgs) and msgs[i + 1].get("kind") == "tool_stack":
            _add_thinking(msg)
            _add_tool_stack(msgs[i + 1])
            i += 2
            continue
        if kind == "thinking":
            _add_thinking(msg)
        elif kind == "tool_stack":
            _add_tool_stack(msg)
        elif kind == "activity":
            _add_activity(msg)
        i += 1

    if not html_parts:
        return ""

    coll_class = " agent-work-collapsed" if collapsed else ""
    content_html = "\n".join(html_parts)
    title = f"Agent work ({_item_count})" if _item_count > 0 else "Agent work"
    return (
        f'<div class="message-row agent-work{coll_class}">'
        f'  <div class="bubble agent-work">'
        f'    <div class="agent-work-title" onclick="_toggleAgentWork(this)">{title}</div>'
        f'    <div class="agent-work-content">{content_html}</div>'
        f'  </div>'
        f'</div>'
    )


# ═══════════════════════════════════════════════════════════════════
#  Core rendering: message list → HTML
# ═══════════════════════════════════════════════════════════════════


def messages_to_html(
    messages: list[dict[str, Any]],
    assistant_stream_index: int | None = None,
    thinking_stream_index: int | None = None,
    page_start: int = 0,
    page_end: int | None = None,
    auto_collapse_count: int = 0,
    auto_collapse_thinking: int = 0,
    auto_collapse_tools: int = 0,
    show_thinking: bool = True,
    show_tools: bool = True,
) -> str:
    """Render a slice of messages to inner HTML (no wrapper).

    Non-turn messages (thinking, tool_stack) between turns are captured
    into a single raw-text bubble.  Pure function — no Qt, no side effects.
    When *show_thinking* or *show_tools* is False, those message kinds
    are omitted from the output.
    """
    if page_end is None:
        page_end = len(messages)

    end = min(page_end, len(messages))

    # Pre-count total agent-work bubbles and thinking blocks.
    total_aw = 0
    total_thinking = 0
    total_tools = 0
    _buf: list = []
    for i in range(page_start, end):
        k = str(messages[i].get("kind", "turn") or "turn")
        if k == "thinking" and not show_thinking:
            continue
        if k == "tool_stack" and not show_tools:
            continue
        if k in _NON_TURN_KINDS or k == "activity":
            _buf.append(messages[i])
            if k == "thinking":
                total_thinking += 1
            elif k == "tool_stack":
                for _item in (messages[i].get("items") or []):
                    if isinstance(_item, dict):
                        total_tools += 1
        else:
            if _buf:
                total_aw += 1
                _buf = []
    if _buf:
        total_aw += 1

    collapse_threshold = total_aw if auto_collapse_count <= 0 else max(0, total_aw - auto_collapse_count)
    thinking_threshold = total_thinking if auto_collapse_thinking <= 0 else max(0, total_thinking - auto_collapse_thinking)
    tools_threshold = total_tools if auto_collapse_tools <= 0 else max(0, total_tools - auto_collapse_tools)
    _thinking_idx: list[int] = [0]
    _tools_idx: list[int] = [0]

    # Single-pass rendering (original logic) with collapse check.
    parts: list[str] = []
    raw_buffer: list[dict[str, Any]] = []
    agent_work_index: int = 0

    for i in range(page_start, end):
        msg = messages[i]
        kind = str(msg.get("kind", "turn") or "turn")

        if kind == "thinking" and not show_thinking:
            continue
        if kind == "tool_stack" and not show_tools:
            continue
        if kind in _NON_TURN_KINDS or kind == "activity":
            raw_buffer.append(msg)
            continue

        # Flush raw buffer before every turn.
        if raw_buffer:
            bubble = _render_raw_activity_bubble(
                raw_buffer,
                collapsed=(agent_work_index < collapse_threshold),
                thinking_threshold=thinking_threshold,
                thinking_counter=_thinking_idx,
                tools_threshold=tools_threshold,
                tools_counter=_tools_idx,
            )
            if bubble:
                parts.append(bubble)
            agent_work_index += 1
            raw_buffer.clear()

        role = str(msg.get("role", "user") or "user")
        content = str(msg.get("content", "") or "")
        meta = msg.get("meta")

        role_class = "user" if role == "human" else "assistant"
        bubble_class = f"bubble {role_class}"
        if i == end - 1 and role == "you":
            bubble_class += " latest"

        if assistant_stream_index is not None and i == assistant_stream_index:
            body_html = (
                f'<div id="assistant-stream-content" '
                f'style="white-space: pre-wrap;">{escape(content)}</div>'
            )
        else:
            body_html = format_content_to_html(content)

        meta_html = f'<div class="meta">{escape(meta)}</div>' if meta else ""
        parts.append(
            f'<div class="message-row {role_class}">'
            f'  <div class="{bubble_class}">{meta_html}{body_html}'
            f'  </div>'
            f'</div>'
        )

    if raw_buffer:
        bubble = _render_raw_activity_bubble(
            raw_buffer,
            collapsed=(agent_work_index < collapse_threshold),
            thinking_threshold=thinking_threshold,
            thinking_counter=_thinking_idx,
            tools_threshold=tools_threshold,
            tools_counter=_tools_idx,
        )
        if bubble:
            parts.append(bubble)

    return "\n".join(parts)



def _build_html_document(
    inner_html: str,
    theme: dict[str, str] | None = None,
    scroll_to_bottom: bool = True,
) -> str:
    """Wrap inner HTML in the full page template."""
    defaults: dict[str, str] = {
        "bg": "#f5f5f7",
        "text": "#000000",
        "bubble_user": "#e3f2fd",
        "bubble_assistant": "#ffffff",
        "meta_text": "#666666",
        "border": "#cccccc",
    }
    colors = {**defaults}
    if theme:
        for k, v in theme.items():
            if k in colors and isinstance(v, str) and v.startswith("#"):
                colors[k] = v

    theme_vars = (
        f"    --bg: {colors['bg']};\n"
        f"    --text: {colors['text']};\n"
        f"    --bubble-user: {colors['bubble_user']};\n"
        f"    --bubble-assistant: {colors['bubble_assistant']};\n"
        f"    --meta-text: {colors['meta_text']};\n"
        f"    --border: {colors['border']};"
    )

    html = HTML_TEMPLATE.replace("/* THEME_VARS */", theme_vars)
    html = html.replace("/* PAGE_NAV_CSS */", _PAGE_NAV_CSS)
    html = html.replace("{messages_html}", inner_html)
    scroll_attr = "1" if scroll_to_bottom else "0"
    html = html.replace("{scroll}", scroll_attr)
    return html


# ═══════════════════════════════════════════════════════════════════
#  ChatRenderer — paginated QWebEngineView wrapper
# ═══════════════════════════════════════════════════════════════════


class ChatRenderer(QWidget):
    """Chat bubble renderer using QWebEngineView.

    Messages are divided into pages of *page_size* user messages each.
    Up to *pages_displayed* pages are rendered at once.
    """

    _SETTINGS_KEY = "llm-thalamus"
    _SETTINGS_ORG = "llm-thalamus"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── WebEngine setup ──────────────────────────────────────
        self._view = QWebEngineView(self)
        self._page = _ChatPage(self._view)
        self._view.setPage(self._page)
        self._view.setZoomFactor(1.0)
        self._view.installEventFilter(self)

        # Allow file:/// URLs in rendered HTML so markdown image
        # references (from [file: ...] expansion) can load local files.
        s = QWebEngineSettings.WebAttribute
        self._view.settings().setAttribute(s(9), True)  # LocalContentCanAccessFileUrls

        # ── Messages ─────────────────────────────────────────────
        self._messages: list[dict[str, Any]] = []
        self._theme: dict[str, str] | None = None

        # ── Pagination ───────────────────────────────────────────
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        self._page_size: int = _settings_int(s, "renderer/page_size", 10)
        self._pages_displayed: int = _settings_int(s, "renderer/pages_displayed", 2)
        self._show_thinking: bool = _settings_int(s, "display/show_thinking", 1) == 1
        self._show_tools: bool = _settings_int(s, "display/show_tools", 1) == 1
        self._auto_collapse_agent_work: int = _settings_int(
            s, "renderer/auto_collapse_agent_work", 2
        )
        self._auto_collapse_thinking: int = _settings_int(
            s, "renderer/auto_collapse_thinking", 2
        )
        self._auto_collapse_tools: int = _settings_int(
            s, "renderer/auto_collapse_tools", 2
        )
        self._display_end_page: int = 0

        # Load saved zoom.
        saved = s.value("chat/zoom")
        if saved is not None:
            try:
                self._view.setZoomFactor(float(saved))
            except (ValueError, TypeError):
                pass

        # ── Streaming state ──────────────────────────────────────
        self._assistant_stream_active: bool = False

        # ── Render control ───────────────────────────────────────
        self._batch_mode: bool = False
        self._render_pending: bool = False
        self._scroll_to_bottom: bool = True

        # Pending deltas for assistant streaming.
        self._page_loaded: bool = False
        self._pending_assistant_deltas: list[str] = []

        # ── Connections ──────────────────────────────────────────
        self._view.loadFinished.connect(self._on_load_finished)
        self._page.copyRequested.connect(self._on_copy_requested)
        self._page.navigatePageRequested.connect(self._on_navigate_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._render()

    # ── Configuration ─────────────────────────────────────────────

    def configure(
        self,
        page_size: int | None = None,
        pages_displayed: int | None = None,
        auto_collapse_agent_work: int | None = None,
        auto_collapse_thinking: int | None = None,
        auto_collapse_tools: int | None = None,
    ) -> None:
        """Update pagination settings and persist to QSettings."""
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        if page_size is not None and page_size > 0:
            self._page_size = page_size
            s.setValue("renderer/page_size", page_size)
        if pages_displayed is not None and pages_displayed > 0:
            self._pages_displayed = pages_displayed
            s.setValue("renderer/pages_displayed", pages_displayed)
        if auto_collapse_agent_work is not None and auto_collapse_agent_work >= 0:
            self._auto_collapse_agent_work = auto_collapse_agent_work
            s.setValue("renderer/auto_collapse_agent_work", auto_collapse_agent_work)
        if auto_collapse_thinking is not None and auto_collapse_thinking >= 0:
            self._auto_collapse_thinking = auto_collapse_thinking
            s.setValue("renderer/auto_collapse_thinking", auto_collapse_thinking)
        if auto_collapse_tools is not None and auto_collapse_tools >= 0:
            self._auto_collapse_tools = auto_collapse_tools
            s.setValue("renderer/auto_collapse_tools", auto_collapse_tools)
        s.sync()
        self._render()

    def set_show_thinking(self, val: bool) -> None:
        self._show_thinking = val
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        s.setValue("display/show_thinking", 1 if val else 0)
        s.sync()
        self._render()

    def set_show_tools(self, val: bool) -> None:
        self._show_tools = val
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        s.setValue("display/show_tools", 1 if val else 0)
        s.sync()
        self._render()

    def set_theme(self, theme: dict[str, str] | None) -> None:
        self._theme = theme
        self._render()

    def persist_zoom(self) -> None:
        s = QSettings(self._SETTINGS_ORG, self._SETTINGS_KEY)
        s.setValue("chat/zoom", self._view.zoomFactor())
        s.sync()

    # ── Zoom (Ctrl+scroll) ────────────────────────────────────────

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self._view and event.type() == QEvent.Type.Wheel:
            we = event
            if we.modifiers() & Qt.ControlModifier:
                factor = self._view.zoomFactor()
                delta = we.angleDelta().y()
                factor = min(3.0, max(0.3, factor + (0.1 if delta > 0 else -0.1)))
                self._view.setZoomFactor(factor)
                return True
        return super().eventFilter(obj, event)

    # ── Batch mode ────────────────────────────────────────────────

    def begin_batch(self) -> None:
        self._batch_mode = True

    def end_batch(self) -> None:
        self._batch_mode = False
        self._display_end_page = self._current_page_index()
        self._render()

    # ── Public data model API ─────────────────────────────────────

    def add_turn(
        self, role: str, text: str, meta: str | None = None
    ) -> None:
        """Add a user or assistant turn."""
        msg: dict[str, Any] = {"kind": "turn", "role": role, "content": text}
        if meta:
            msg["meta"] = meta

        old_page = self._current_page_index()
        self._messages.append(msg)
        new_page = self._current_page_index()

        # Finalize any in-progress assistant stream.
        self._assistant_stream_active = False
        self._pending_assistant_deltas.clear()

        if self._batch_mode:
            return

        if role == "human":
            # Render through format_content_to_html so [file: ...]
            # references are converted to inline media.
            html = format_content_to_html(text)
            if new_page != old_page:
                self._display_end_page = new_page
                self._render()
            else:
                # Large HTML can overflow the JS bridge string limit.
                # Fall back to a full re-render when the payload
                # exceeds 50 KB.
                if len(html) > 50_000:
                    self._render()
                else:
                    self._exec_js(
                        "_appendUserBubble(" + json.dumps(html) + ")"
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
        self._messages.append(
            {"kind": "turn", "role": "human", "content": text}
        )
        self._exec_js("_appendUserBubble(" + json.dumps(escape(text)) + ")")

    # ── Thinking API (data model only, no DOM) ─────────────────────

    def add_thinking(self, text: str | None = None) -> None:
        """Add a thinking block.  ``text=None`` starts a live accumulation."""
        self._messages.append({
            "kind": "thinking",
            "text": text or "",
            "expanded": text is None,
        })

    def append_thinking_delta(self, text: str) -> None:
        """Append text to the last thinking message (in-memory only)."""
        if not text:
            return
        # Find the last thinking message.
        for msg in reversed(self._messages):
            if msg.get("kind") == "thinking":
                msg["text"] = msg.get("text", "") + text
                break

    def end_thinking(self) -> None:
        """Finalize the last thinking block."""
        for msg in reversed(self._messages):
            if msg.get("kind") == "thinking":
                msg["expanded"] = False
                break

    # ── Tool event API (data model only, no DOM) ──────────────────

    def upsert_tool_event(
        self, stack_id: str, event: dict[str, Any]
    ) -> None:
        """Create or update a tool stack (in-memory only)."""
        stack = self._ensure_tool_stack(stack_id)
        event_type = str(event.get("event_type") or "")
        tool_call_id = str(event.get("tool_call_id") or "")
        need_render = False
        item = self._ensure_tool_stack_item(
            stack,
            tool_call_id=tool_call_id,
            event=event,
        )

        if event_type == "tool_call":
            existing_status = str(item.get("status") or "")
            tool_name = str(
                event.get("tool_name") or item.get("tool_name") or "tool"
            )
            item.update({
                "tool_name": tool_name,
                "tool_kind": event.get("tool_kind"),
                "mcp_server_id": event.get("mcp_server_id"),
                "mcp_remote_name": event.get("mcp_remote_name"),
                "step": event.get("step"),
                "args": event.get("args"),
            })
            args_val = event.get("args")
            if isinstance(args_val, dict):
                item["_fmt_args"] = _format_json_block(args_val)
            if existing_status != "pending_approval":
                item["status"] = "running"

        elif event_type == "tool_update":
            partial = event.get("partial_result", "")
            if partial and partial != item.get("_partial_text"):
                item["_partial_text"] = partial
                item["_fmt_stream"] = escape(partial)
                item["status"] = "running"
                need_render = True
            details = event.get("details")
            if isinstance(details, dict) and details:
                item["_fmt_running_details"] = {
                    "progress": details.get("progress"),
                    "results": details.get("results"),
                }
                need_render = True

        elif event_type == "tool_result":
            result = event.get("result")
            status = "ok" if bool(event.get("ok", False)) else "error"
            if isinstance(result, dict):
                error = result.get("error")
                if (
                    isinstance(error, dict)
                    and str(error.get("code") or "") == "tool_denied"
                ):
                    status = "denied"
            item.update({
                "tool_name": str(
                    event.get("tool_name") or item.get("tool_name") or "tool"
                ),
                "tool_kind": event.get("tool_kind"),
                "mcp_server_id": event.get("mcp_server_id"),
                "mcp_remote_name": event.get("mcp_remote_name"),
                "step": event.get("step"),
                "result": result,
                "error": event.get("error"),
                "status": status,
            })
            if result is not None:
                item["_fmt_result"] = _format_json_block(result)
            item.pop("_partial_text", None)
            item.pop("_fmt_stream", None)
            details = event.get("details")
            if isinstance(details, dict):
                item["_fmt_details"] = _format_subagent_details(details)
            need_render = True

        if need_render:
            self._request_render()

    # ── Streaming assistant API ───────────────────────────────────

    def begin_assistant_stream(self) -> None:
        """Start streaming assistant text.  Add the turn to ``_messages``
        immediately so that tool events arrive AFTER it in the list.
        """
        self._messages.append({
            "kind": "turn", "role": "you", "content": "",
        })
        self._assistant_stream_active = True
        self._streaming_assistant_content: str = ""
        self._pending_assistant_deltas.clear()
        self._page_loaded = True
        self._exec_js("_beginAssistantBubble()")

    def append_assistant_delta(self, text: str) -> None:
        if not self._assistant_stream_active or not text:
            return

        self._streaming_assistant_content += text
        # Keep the turn in _messages in sync.
        for msg in reversed(self._messages):
            if msg.get("kind") == "turn" and msg.get("role") == "you":
                msg["content"] = msg.get("content", "") + text
                break

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
        self._request_render()

    # ── Clear ─────────────────────────────────────────────────────

    def clear(self) -> None:
        self._messages.clear()
        self._display_end_page = 0
        self._assistant_stream_active = False
        self._pending_assistant_deltas.clear()
        self._render()

    # ── Internal helpers ─────────────────────────────────────────

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

    # ── Pagination helpers ────────────────────────────────────────

    def _user_message_indices(self) -> list[int]:
        return [
            i
            for i, m in enumerate(self._messages)
            if isinstance(m, dict)
            and m.get("kind") == "turn"
            and m.get("role") == "human"
        ]

    def _current_page_index(self) -> int:
        user_idx = self._user_message_indices()
        if not user_idx:
            return 0
        return (len(user_idx) - 1) // self._page_size

    def _total_pages(self) -> int:
        user_idx = self._user_message_indices()
        if not user_idx:
            return 1
        return max(1, (len(user_idx) + self._page_size - 1) // self._page_size)

    def _page_message_range(self, page_index: int) -> tuple[int, int] | None:
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
        total = self._total_pages()
        start = max(0, self._display_end_page - self._pages_displayed + 1)
        end = min(total, self._display_end_page + 1)
        return list(range(start, end))

    # ── Tool stack management (data model only) ───────────────────

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
        event: dict[str, Any],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = stack.setdefault("items", [])
        if not isinstance(items, list):
            items = []
            stack["items"] = items

        # Try to find by tool_call_id.
        if tool_call_id:
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                if str(item.get("tool_call_id") or "") != tool_call_id:
                    continue
                item.setdefault("stack_id", str(stack.get("stack_id") or ""))
                return item

        # Create new item.
        item: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "tool_name": str(event.get("tool_name") or "tool"),
            "stack_id": str(stack.get("stack_id") or ""),
            "item_key": str(tool_call_id or len(items)),
            "expanded": False,
        }
        items.append(item)
        return item

    # ── Page navigation ───────────────────────────────────────────

    def _on_navigate_page(self, page_index: int) -> None:
        total = self._total_pages()
        if 0 <= page_index < total:
            self._display_end_page = page_index
            self._scroll_to_bottom = True
            self._render()

    # ── Copy handler ─────────────────────────────────────────────

    def _on_copy_requested(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    # ── Render ────────────────────────────────────────────────────

    def _render(self) -> None:
        if self._batch_mode:
            return

        self._page_loaded = False

        # Follow the latest page during streaming.
        if self._assistant_stream_active:
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
                messages_to_html(
                    self._messages,
                    assistant_stream_index=None,
                    page_start=s,
                    page_end=e,
                    auto_collapse_count=self._auto_collapse_agent_work,
                    auto_collapse_thinking=self._auto_collapse_thinking,
                    auto_collapse_tools=self._auto_collapse_tools,
                    show_thinking=self._show_thinking,
                    show_tools=self._show_tools,
                )
            )

        # Build with navigation dividers.
        all_parts: list[str] = []
        if visible_pages:
            nav = _page_nav_html(
                visible_pages[0], visible_pages[-1], total_pages
            )
            all_parts.append(nav)
            for idx, ph in enumerate(page_htmls):
                all_parts.append(ph)
                if idx < len(page_htmls) - 1:
                    all_parts.append(nav)
            all_parts.append(nav)

        messages_html = "\n".join(all_parts)
        html = _build_html_document(
            messages_html,
            theme=self._theme,
            scroll_to_bottom=self._scroll_to_bottom,
        )
        self._scroll_to_bottom = True
        self._view.setHtml(html, QUrl("file:///"))

    # ── Stream delta helpers ──────────────────────────────────────

    def _append_stream_delta_js(self, text: str) -> None:
        self._view.page().runJavaScript(
            "window.thalamusAppendAssistantDelta("
            + json.dumps("assistant-stream-content")
            + ","
            + json.dumps(text)
            + ");"
        )

    # ── Page load callback ────────────────────────────────────────

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = bool(ok)
        if not self._page_loaded:
            return

        # Drain pending deltas.
        if self._assistant_stream_active:
            if self._pending_assistant_deltas:
                for d in self._pending_assistant_deltas:
                    self._append_stream_delta_js(d)
                self._pending_assistant_deltas.clear()
            # No formatted code blocks during streaming — skip enhancement.
            return

        self._pending_assistant_deltas.clear()
        self._view.page().runJavaScript("enhanceCodeBlocks()")


# ── Module-level utility ───────────────────────────────────────────


def _settings_int(s: QSettings, key: str, default: int) -> int:
    try:
        return int(s.value(key))
    except (ValueError, TypeError):
        return default
