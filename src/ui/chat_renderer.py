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


class _ChatPage(QWebEnginePage):
    toolStackToggleRequested = Signal(str)
    toolStackItemToggleRequested = Signal(str, str)
    thinkingToggleRequested = Signal(int)
    copyRequested = Signal(str)

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
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


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
    if expanded:
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
        body_html = f'<div>{"".join(body_parts)}{actions_html}</div>'

    return (
        '<div class="tool-stack-item">'
        '  <div class="tool-stack-item-header">'
        f'    <div class="tool-stack-item-title">{escape(tool_name)}</div>'
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
    items_html = ""
    if expanded:
        rendered_items = []
        for item in items:
            if pending_item is not None and item is pending_item:
                continue
            rendered_items.append(_render_tool_stack_item(item))
        if rendered_items:
            items_html = f'<div class="tool-stack-items">{"".join(rendered_items)}</div>'
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

    content_html = ""
    if expanded:
        if thinking_stream_index is not None and idx == thinking_stream_index:
            content_html = (
                f'<div id="thinking-stream-content-{idx}" '
                f'class="thinking-content">{escape(thinking_text)}</div>'
            )
        else:
            content_html = (
                f'<div class="thinking-content">'
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
) -> None:
    """Render accumulated thinking/tool items as an 'agent-work' collapsible group."""
    if not group_items:
        return

    count = len(group_items)
    # The group is expanded (visible) if the active thinking stream index falls
    # anywhere inside it — i.e. the agent is still streaming reasoning.
    expanded = any(
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


def render_chat_html(
    messages: List[Dict[str, Any]],
    theme: Optional[Dict[str, str]] = None,
    assistant_stream_index: int | None = None,
    thinking_stream_index: int | None = None,
    scroll_to_bottom: bool = True,
    body_html_cache: dict[int, str] | None = None,
) -> str:
    parts: List[str] = []

    # Accumulator for consecutive thinking / tool_stack / activity items
    # that appear between turns.  Flushed as an agent-work group before
    # each user or assistant bubble.
    agent_work_buffer: list[tuple[str, int, dict]] = []

    for i, msg in enumerate(messages):
        kind = str(msg.get("kind", "turn") or "turn")
        content = str(msg.get("content", "") or "")
        meta = msg.get("meta")

        if kind in NON_TURN_KINDS:
            agent_work_buffer.append((kind, i, msg))
            continue

        # ── turn row (user or assistant) — flush any buffered agent work first ──
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
        elif body_html_cache is not None and i in body_html_cache:
            body_html = body_html_cache[i]
        else:
            body_html = format_content_to_html(content)
            if body_html_cache is not None:
                body_html_cache[i] = body_html

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

    # Flush any agent work at end of messages (common during streaming).
    _flush_agent_work_group(agent_work_buffer, parts, thinking_stream_index)

    messages_html = "\n".join(parts)

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
    html = html.replace("{messages_html}", messages_html)
    scroll_attr = "1" if scroll_to_bottom else "0"
    html = html.replace("{scroll}", scroll_attr)
    return html


class ChatRenderer(QWidget):
    """A small wrapper around QWebEngineView that renders chat bubbles via HTML."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._view = QWebEngineView(self)
        self._page = _ChatPage(self._view)
        self._view.setPage(self._page)
        self._view.setZoomFactor(1.0)
        # Restore saved chat zoom.
        saved = QSettings("llm-thalamus", "llm-thalamus").value("chat/zoom")
        if saved is not None:
            try:
                self._view.setZoomFactor(float(saved))
            except (ValueError, TypeError):
                pass
        self._view.installEventFilter(self)
        self._messages: list[dict[str, Any]] = []
        self._theme: dict[str, str] | None = None

        # Streaming state (UI is turn-locked, so only one assistant stream can be active).
        self._assistant_stream_active: bool = False
        self._assistant_stream_index: int | None = None

        # Thinking streaming state — independent of assistant streaming.
        self._thinking_stream_active: bool = False
        self._thinking_stream_index: int | None = None

        # When True, the next full render will scroll to bottom on page load.
        # Toggle actions (Show/Hide) set this to False to preserve position.
        self._scroll_to_bottom: bool = True

        # When set, the next page load will scroll to this element id.
        # Used by toggle actions to keep the toggled element visible.
        self._toggle_scroll_target: str | None = None

        # If deltas arrive before the page finishes loading after begin_assistant_stream() or
        # add_thinking(), buffer them and flush once loadFinished fires.
        self._page_loaded: bool = False
        self._pending_assistant_deltas: list[str] = []
        self._pending_thinking_deltas: list[str] = []

        self._view.loadFinished.connect(self._on_load_finished)
        self._page.toolStackToggleRequested.connect(self._on_tool_stack_toggle_requested)
        self._page.toolStackItemToggleRequested.connect(self._on_tool_stack_item_toggle_requested)
        self._page.thinkingToggleRequested.connect(self._on_thinking_toggle)
        self._page.copyRequested.connect(self._on_copy_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._batch_mode: bool = False
        self._render_pending: bool = False
        # Cached rendered body HTML for each message index (keyed by index).
        # Invalidation: entries at or after the first streaming-affected index
        # are cleared before each render, so marks are only reused for
        # messages that have *finished* streaming.
        self._body_html_cache: dict[int, str] = {}
        self._render()

    def begin_batch(self) -> None:
        """Suppress renders until ``end_batch()`` is called.

        Used during history loading to avoid hundreds of individual
        ``setHtml()`` calls — all messages are accumulated silently,
        then a single render paints everything at once.
        """
        self._batch_mode = True

    def end_batch(self) -> None:
        """Flush accumulated messages with a single render."""
        self._batch_mode = False
        self._render()

    def _request_render(self) -> None:
        """Schedule a deferred render via QTimer.singleShot(0).

        Multiple calls within the same event-loop tick coalesce into one
        ``setHtml()``, so rapid-fire events (thinking_start→end,
        tool_execution_start→end) trigger fewer full page loads.

        Does NOT replace direct ``_render()`` calls from user actions
        (add_turn, toggle) or streaming lifecycle methods.
        """
        if self._render_pending:
            return
        self._render_pending = True
        QTimer.singleShot(0, self._do_deferred_render)

    def _do_deferred_render(self) -> None:
        self._render_pending = False
        self._render()

    def add_turn(self, role: str, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "turn", "role": role, "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)

        # Any explicit add_turn finalizes any in-progress assistant stream.
        # Leave thinking stream untouched — it's independent.
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._pending_assistant_deltas.clear()

        # Force immediate render for discrete turns.
        # The render itself checks _batch_mode and skips if true.
        self._render()

    def add_activity(self, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "activity", "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)

        # Activity rows must not finalize or corrupt an active assistant stream.
        self._render()

    def add_steer_message(self, text: str) -> None:
        """Add a user turn during steering without touching assistant streaming."""
        msg: dict[str, Any] = {"kind": "turn", "role": "human", "content": text}
        self._messages.append(msg)
        self._render()

    # --- Thinking bubble API ---------------------------------------------------

    def add_thinking(self, text: str | None = None) -> None:
        """Add a thinking bubble.

        If *text* is ``None`` the bubble is a live streaming target (starts
        expanded so the user can follow the reasoning in real-time).
        When *text* is provided the bubble is static history content (collapsed
        by default).
        """
        msg: dict[str, Any] = {
            "kind": "thinking",
            "text": text or "",
            "expanded": text is None,  # expanded during live, collapsed for history
        }
        self._messages.append(msg)

        if text is None:
            self._thinking_stream_active = True
            self._thinking_stream_index = len(self._messages) - 1
            self._request_render()
        else:
            self._thinking_stream_active = False
            self._thinking_stream_index = None
            self._request_render()

    def append_thinking_delta(self, text: str) -> None:
        """Append streaming text to the active thinking bubble (JS DOM patch)."""
        if not self._thinking_stream_active:
            return
        if self._thinking_stream_index is None:
            return
        if not text:
            return

        # Keep canonical source-of-truth updated.
        self._messages[self._thinking_stream_index]["text"] += text

        if not self._page_loaded:
            self._pending_thinking_deltas.append(text)
            return

        self._append_thinking_delta_js(text)

    def end_thinking(self) -> None:
        """Finalize the active thinking bubble.

        Flushes any buffered deltas, collapses the bubble, and does a full
        re-render.
        """
        # Flush any queued thinking deltas.
        if self._pending_thinking_deltas:
            if self._page_loaded:
                for d in self._pending_thinking_deltas:
                    self._append_thinking_delta_js(d)
            self._pending_thinking_deltas.clear()

        if self._thinking_stream_index is not None:
            self._messages[self._thinking_stream_index]["expanded"] = False

        self._thinking_stream_active = False
        self._thinking_stream_index = None
        self._request_render()

    # -------------------------------------------------------------------

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
            item.update(
                {
                    "tool_name": str(event.get("tool_name") or item.get("tool_name") or "tool"),
                    "tool_kind": event.get("tool_kind"),
                    "mcp_server_id": event.get("mcp_server_id"),
                    "mcp_remote_name": event.get("mcp_remote_name"),
                    "step": event.get("step"),
                    "args": event.get("args"),
                }
            )
            # Cache formatted args for rendering.
            args_val = event.get("args")
            if isinstance(args_val, dict):
                item["_fmt_args"] = _format_json_block(args_val)
            if existing_status != "pending_approval":
                item["status"] = "running"
            # Clear any stale streaming state from a previous call.
            item.pop("_partial_text", None)
            item.pop("_fmt_stream", None)
            self._request_render()
        elif event_type == "tool_update":
            # Streaming partial output while the tool is still running.
            # The subagent extension sends the *full* accumulated text
            # on every update — replace, don't append.
            partial = event.get("partial_result", "")
            if partial and partial != item.get("_partial_text"):
                item["_partial_text"] = partial
                item["_fmt_stream"] = escape(partial)
                item["status"] = "running"
                self._request_render()
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
            # Cache formatted result for rendering.
            if result is not None:
                item["_fmt_result"] = _format_json_block(result)
            # Clear streaming state — final result replaces it.
            item.pop("_partial_text", None)
            item.pop("_fmt_stream", None)
            # Extract subagent details for rendering in the tool card.
            details = event.get("details")
            if isinstance(details, dict):
                item["_fmt_details"] = _format_subagent_details(details)
            self._request_render()

    # --- Streaming assistant API ---

    def begin_assistant_stream(self) -> None:
        """Create an empty assistant bubble and prepare to append streaming deltas."""
        msg: dict[str, Any] = {"kind": "turn", "role": "you", "content": ""}
        self._messages.append(msg)
        self._assistant_stream_active = True
        self._assistant_stream_index = len(self._messages) - 1
        self._pending_assistant_deltas.clear()

        # Immediate full render so the empty bubble appears and the stream DOM target exists.
        self._render()

    def append_assistant_delta(self, text: str) -> None:
        """Append streaming text to the current assistant bubble (DOM patch; no reload)."""
        if not self._assistant_stream_active:
            return
        if self._assistant_stream_index is None:
            return
        if not text:
            return

        # Always keep the canonical source-of-truth updated.
        self._messages[self._assistant_stream_index]["content"] += text

        # If the page isn't ready yet (immediately after begin_assistant_stream render),
        # buffer deltas and flush once loadFinished fires.
        if not self._page_loaded:
            self._pending_assistant_deltas.append(text)
            return

        self._append_stream_delta_js(text)

    def end_assistant_stream(self) -> None:
        """Finalize assistant streaming."""
        # Ensure any queued deltas are applied before the final render.
        if self._pending_assistant_deltas:
            if self._page_loaded:
                for d in self._pending_assistant_deltas:
                    self._append_stream_delta_js(d)
            self._pending_assistant_deltas.clear()

        self._assistant_stream_active = False
        self._assistant_stream_index = None

        # One final full render to apply markdown, highlighting, katex, etc.
        self._render()

    # ---------------------------------------------------------------------------

    def set_theme(self, theme: dict[str, str] | None) -> None:
        self._theme = theme
        self._render()

    def clear(self) -> None:
        self._messages.clear()
        self._body_html_cache.clear()
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
                # Persist zoom.
                QSettings("llm-thalamus", "llm-thalamus").setValue("chat/zoom", factor)
                return True
        return super().eventFilter(obj, event)

    # ---------------------------------------------------------------------------

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = bool(ok)

        if not self._page_loaded:
            return

        # Flush any buffered assistant deltas.
        if self._assistant_stream_active and self._assistant_stream_index is not None:
            if self._pending_assistant_deltas:
                for d in self._pending_assistant_deltas:
                    self._append_stream_delta_js(d)
                self._pending_assistant_deltas.clear()
        else:
            # No active assistant stream — discard stale assistant deltas.
            self._pending_assistant_deltas.clear()

        # Flush any buffered thinking deltas.
        if self._thinking_stream_active and self._thinking_stream_index is not None:
            if self._pending_thinking_deltas:
                for d in self._pending_thinking_deltas:
                    self._append_thinking_delta_js(d)
                self._pending_thinking_deltas.clear()
        else:
            # No active thinking stream — discard stale thinking deltas.
            self._pending_thinking_deltas.clear()

        # Re-apply code-block enhancements (copy button) on every page load.
        self._view.page().runJavaScript("enhanceCodeBlocks()")
        # Re-apply agent-work group click handlers.
        self._view.page().runJavaScript("enhanceAgentWorkGroups()")

        # Scroll to the toggled element if set, or to bottom if _scroll_to_bottom is True.
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

    def _on_tool_stack_toggle_requested(self, stack_id: str) -> None:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            return
        stack["expanded"] = not bool(stack.get("expanded", False))
        # When expanding the stack, expand all items too (one-click expansion).
        if stack.get("expanded"):
            for item in stack.get("items", []):
                if isinstance(item, dict):
                    item["expanded"] = True
        self._scroll_to_bottom = False
        self._toggle_scroll_target = f"tool-stack-{stack_id}"
        self._render()

    def _on_tool_stack_item_toggle_requested(self, stack_id: str, item_key: str) -> None:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            return
        items = stack.get("items", [])
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("item_key") or "") != item_key:
                continue
            item["expanded"] = not bool(item.get("expanded", False))
            break
        self._scroll_to_bottom = False
        self._toggle_scroll_target = f"tool-stack-{stack_id}"
        self._render()

    def _on_copy_requested(self, text: str) -> None:
        """Copy code-block text to the system clipboard.

        Feedback ('Copied!') is handled in JavaScript before the
        navigation, so we only need to set the clipboard here.
        """
        QGuiApplication.clipboard().setText(text)

    def _on_thinking_toggle(self, index: int) -> None:
        """Toggle expand/collapse on a thinking bubble."""
        if 0 <= index < len(self._messages):
            msg = self._messages[index]
            if isinstance(msg, dict) and msg.get("kind") == "thinking":
                msg["expanded"] = not bool(msg.get("expanded", False))
                self._scroll_to_bottom = False
                self._toggle_scroll_target = f"thinking-{index}"
                self._render()

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
        # During batch mode (history loading), suppress renders until flush.
        if self._batch_mode:
            self._scroll_to_bottom = True  # don't let it get stale
            return

        # Any full render resets the page. We'll re-arm _page_loaded via loadFinished.
        self._page_loaded = False

        # Invalidate cache entries that belong to the active streaming zone.
        # The earliest affected index is the start of the first streaming
        # message; everything at or after it must be re-rendered.
        first_live = None
        if self._thinking_stream_active and self._thinking_stream_index is not None:
            first_live = self._thinking_stream_index
        if self._assistant_stream_active and self._assistant_stream_index is not None:
            sl = self._assistant_stream_index
            if first_live is None or sl < first_live:
                first_live = sl
        if first_live is not None:
            stale = [k for k in self._body_html_cache if k >= first_live]
            for k in stale:
                del self._body_html_cache[k]

        html = render_chat_html(
            self._messages,
            theme=self._theme,
            assistant_stream_index=self._assistant_stream_index if self._assistant_stream_active else None,
            thinking_stream_index=self._thinking_stream_index if self._thinking_stream_active else None,
            scroll_to_bottom=self._scroll_to_bottom,
            body_html_cache=self._body_html_cache,
        )
        self._scroll_to_bottom = True  # default back for next normal update
        self._view.setHtml(html, QUrl("file:///"))
