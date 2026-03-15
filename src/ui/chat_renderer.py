from __future__ import annotations

from typing import List, Dict, Optional, Any
from html import escape
import re
import json
from urllib.parse import quote, unquote

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Signal
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
    border-radius: 999px;
    padding: 4px 10px;
    background: rgba(240, 242, 246, 0.82);
    color: var(--text);
    font-size: 12px;
    line-height: 1.25;
}

.tool-stack-summary {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
}

.tool-stack-toggle {
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
    flex: 0 0 auto;
}

.tool-stack-summary-text {
    overflow-x: auto;
    overflow-y: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    scrollbar-width: none;
    flex: 1 1 auto;
}

.tool-stack-summary-text::-webkit-scrollbar {
    display: none;
}

.tool-stack-pending {
    margin-top: 8px;
    border: 1px solid #b36b00;
    background: #fff5db;
    border-radius: 8px;
    padding: 8px 10px;
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

.tool-stack-actions {
    margin-top: 8px;
    display: flex;
    gap: 8px;
}

.tool-stack-action {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    text-decoration: none;
    font-weight: 600;
    border: 1px solid transparent;
}

.tool-stack-action.approve {
    background: #2e7d32;
    border-color: #1b5e20;
    color: white;
}

.tool-stack-action.deny {
    background: white;
    border-color: #c62828;
    color: #c62828;
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

            function showCopied() {
                var old = button.textContent;
                button.textContent = 'Copied!';
                setTimeout(function() {
                    button.textContent = old;
                }, 1200);
            }

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(showCopied).catch(function() {
                    var textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    try { document.execCommand('copy'); } catch (e) {}
                    document.body.removeChild(textarea);
                    showCopied();
                });
            } else {
                var textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                try { document.execCommand('copy'); } catch (e) {}
                document.body.removeChild(textarea);
                showCopied();
            }
        });

        pre.appendChild(button);
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

document.addEventListener("DOMContentLoaded", function() {
    prettifyJsonBlocks();
    highlightCodeBlocks();
    enhanceCodeBlocks();
    renderMathNodes();

    _scrollToBottom();
    requestAnimationFrame(function() {
        document.body.setAttribute("data-ready", "1");
    });
});
</script>
</head>

<body data-ready="0">
<div class="chat-container">
{messages_html}
</div>
</body>
</html>
"""


class _ChatPage(QWebEnginePage):
    toolStackToggleRequested = Signal(str)
    toolApprovalActionRequested = Signal(str, str, str)

    def createWindow(self, _type):
        # Tool stack controls are handled in-page; never spawn a second WebEngine window.
        return self

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "thalamus" and url.host() == "toggle-tool-stack":
            stack_id = url.path().lstrip("/")
            if stack_id:
                self.toolStackToggleRequested.emit(stack_id)
            return False
        if url.scheme() == "thalamus" and url.host() == "tool-approval":
            parts = [unquote(part) for part in url.path().split("/") if part]
            if len(parts) == 3:
                action, stack_id, request_id = parts
                if action in {"approve-once", "deny-once", "always-allow", "always-deny"} and stack_id and request_id:
                    self.toolApprovalActionRequested.emit(
                        stack_id,
                        request_id,
                        action,
                    )
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
        return escape(json.dumps(value, ensure_ascii=False, indent=2))
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


def _node_status_summary(msg: Dict[str, Any]) -> str:
    status = str(msg.get("node_status") or "")
    if status == "running":
        return "running"
    if status == "ok":
        return "complete"
    if status == "error":
        return "failed"
    return ""


def _tool_stack_summary(msg: Dict[str, Any]) -> str:
    items = [it for it in msg.get("items", []) if isinstance(it, dict)]
    node_id = str(msg.get("node_id") or "node")
    parts: list[str] = [node_id]
    node_status = _node_status_summary(msg)
    if node_status:
        parts.append(node_status)
    pending = next((it for it in items if str(it.get("status") or "") == "pending_approval"), None)
    if pending is not None:
        tool_name = str(pending.get("tool_name") or "tool")
        parts.append(f"awaiting approval: {tool_name}")
    else:
        for item in items:
            tool_name = str(item.get("tool_name") or "tool")
            status = str(item.get("status") or "running")
            if status == "pending_approval":
                label = "awaiting approval"
            elif status == "ok":
                label = "ok"
            elif status == "error":
                label = "failed"
            elif status == "denied":
                label = "denied"
            else:
                label = "running"
            parts.append(f"{tool_name} {label}")
    return " - ".join(part for part in parts if part)


def _render_tool_stack_item(item: Dict[str, Any]) -> str:
    tool_name = str(item.get("tool_name") or "tool")
    status_label, badge_class = _tool_item_status_label(item)
    meta_parts: list[str] = []
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

    actions_html = ""
    request_id = str(item.get("request_id") or "")
    stack_id = str(item.get("stack_id") or "")
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
        f'    <div class="tool-stack-badge {badge_class}">{escape(status_label)}</div>'
        '  </div>'
        f'{meta_html}'
        f'{body_html}'
        '</div>'
    )


def render_chat_html(
    messages: List[Dict[str, Any]],
    theme: Optional[Dict[str, str]] = None,
    assistant_stream_index: int | None = None,
) -> str:
    parts: List[str] = []

    for i, msg in enumerate(messages):
        kind = str(msg.get("kind", "turn") or "turn")
        content = str(msg.get("content", "") or "")
        meta = msg.get("meta")

        if kind == "tool_stack":
            stack_id = str(msg.get("stack_id") or "")
            collapsed_summary = _tool_stack_summary(msg)
            expanded = bool(msg.get("expanded", False))
            items = [it for it in msg.get("items", []) if isinstance(it, dict)]
            pending_item = next((it for it in items if str(it.get("status") or "") == "pending_approval"), None)

            summary_html = (
                '<div class="tool-stack-summary">'
                f'<a class="tool-stack-toggle" href="thalamus://toggle-tool-stack/{escape(stack_id)}">'
                f'{"Hide" if expanded else "Show"}</a>'
                f'<div class="tool-stack-summary-text">{escape(collapsed_summary)}</div>'
                '</div>'
            )

            pending_html = ""
            if pending_item is not None:
                pending_html = (
                    '<div class="tool-stack-pending">'
                    f'{_render_tool_stack_item(pending_item)}'
                    '</div>'
                )
            parts.append(
                '<div class="tool-stack-row">'
                f'  <div class="tool-stack-card">{summary_html}{pending_html}</div>'
                '</div>'
            )
            continue

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
    return html


class ChatRenderer(QWidget):
    """A small wrapper around QWebEngineView that renders chat bubbles via HTML."""

    toolApprovalActionRequested = Signal(str, str, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._view = QWebEngineView(self)
        self._page = _ChatPage(self._view)
        self._view.setPage(self._page)
        self._messages: list[dict[str, Any]] = []
        self._theme: dict[str, str] | None = None

        # Streaming state (UI is turn-locked, so only one assistant stream can be active).
        self._assistant_stream_active: bool = False
        self._assistant_stream_index: int | None = None

        # If deltas arrive before the page finishes loading after begin_assistant_stream(),
        # buffer them and flush once loadFinished fires.
        self._page_loaded: bool = False
        self._pending_stream_deltas: list[str] = []

        self._view.loadFinished.connect(self._on_load_finished)
        self._page.toolStackToggleRequested.connect(self._on_tool_stack_toggle_requested)
        self._page.toolApprovalActionRequested.connect(self.toolApprovalActionRequested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._render()

    def add_turn(self, role: str, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "turn", "role": role, "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)

        # Any explicit add_turn finalizes any in-progress assistant stream.
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._pending_stream_deltas.clear()

        # Force immediate render for discrete turns.
        self._render()

    def add_activity(self, text: str, meta: str | None = None) -> None:
        msg: dict[str, Any] = {"kind": "activity", "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)

        # Activity rows must not finalize or corrupt an active assistant stream.
        self._render()

    def upsert_tool_event(self, stack_id: str, event: dict[str, Any]) -> None:
        stack = self._ensure_tool_stack(
            stack_id,
            node_id=str(event.get("node_id") or ""),
            span_id=str(event.get("span_id") or ""),
        )
        event_type = str(event.get("event_type") or "")
        if event_type == "node_start":
            stack["node_status"] = "running"
            self._render()
            return
        if event_type == "node_end":
            status = str(event.get("status") or "ok")
            stack["node_status"] = "error" if status == "error" else "ok"
            if not self._stack_has_pending(stack):
                stack["expanded"] = False
            self._render()
            return
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
            if existing_status != "pending_approval":
                item["status"] = "running"
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
            if not self._stack_has_pending(stack):
                stack["expanded"] = False

        self._render()

    def set_tool_approval_pending(self, stack_id: str, payload: dict[str, Any]) -> None:
        stack = self._ensure_tool_stack(
            stack_id,
            node_id=str(payload.get("node_id") or ""),
            span_id=str(payload.get("span_id") or ""),
        )
        tool_call_id = str(payload.get("tool_call_id") or "")
        request_id = str(payload.get("request_id") or "")
        item = self._ensure_tool_stack_item(
            stack,
            tool_call_id=tool_call_id,
            request_id=request_id,
            event_type="approval_request",
            event=payload,
        )
        item.update(
            {
                "tool_name": str(payload.get("tool_name") or item.get("tool_name") or "tool"),
                "tool_kind": payload.get("tool_kind"),
                "mcp_server_id": payload.get("mcp_server_id"),
                "mcp_remote_name": payload.get("mcp_remote_name"),
                "step": payload.get("step"),
                "args": payload.get("args"),
                "description": payload.get("description"),
                "request_id": request_id,
                "status": "pending_approval",
            }
        )
        stack["expanded"] = True
        self._render()

    def resolve_tool_approval_pending(self, stack_id: str, request_id: str, approved: bool) -> None:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            return
        for item in stack.get("items", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("request_id") or "") != request_id:
                continue
            item["status"] = "running" if approved else "denied"
            if not approved:
                item["error"] = "Approval denied."
            break
        if not self._stack_has_pending(stack):
            stack["expanded"] = False
        self._render()

    def get_pending_tool_approval(self, stack_id: str, request_id: str) -> dict[str, Any] | None:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            return None
        for item in stack.get("items", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("request_id") or "") != request_id:
                continue
            if str(item.get("status") or "") != "pending_approval":
                continue
            return dict(item)
        return None

    # --- Streaming assistant API -------------------------------------------------

    def begin_assistant_stream(self) -> None:
        """Create an empty assistant bubble and prepare to append streaming deltas."""
        msg: dict[str, Any] = {"kind": "turn", "role": "you", "content": ""}
        self._messages.append(msg)
        self._assistant_stream_active = True
        self._assistant_stream_index = len(self._messages) - 1
        self._pending_stream_deltas.clear()

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
            self._pending_stream_deltas.append(text)
            return

        self._append_stream_delta_js(text)

    def end_assistant_stream(self) -> None:
        """Finalize assistant streaming."""
        # Ensure any queued deltas are applied before the final render.
        if self._pending_stream_deltas:
            if self._page_loaded:
                for d in self._pending_stream_deltas:
                    self._append_stream_delta_js(d)
            self._pending_stream_deltas.clear()

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
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._pending_stream_deltas.clear()
        self._render()

    # ---------------------------------------------------------------------------

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = bool(ok)

        # If we were streaming and deltas arrived before load finished, flush them now.
        if not self._page_loaded:
            return
        if not self._assistant_stream_active:
            self._pending_stream_deltas.clear()
            return
        if self._assistant_stream_index is None:
            self._pending_stream_deltas.clear()
            return

        if self._pending_stream_deltas:
            for d in self._pending_stream_deltas:
                self._append_stream_delta_js(d)
            self._pending_stream_deltas.clear()

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

    def _ensure_tool_stack(self, stack_id: str, *, node_id: str = "", span_id: str = "") -> dict[str, Any]:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            stack = {
                "kind": "tool_stack",
                "stack_id": stack_id,
                "expanded": False,
                "items": [],
                "node_id": "",
                "span_id": "",
                "node_status": "",
            }
            self._messages.append(stack)

        if span_id:
            stack["span_id"] = span_id
        if node_id:
            stack["node_id"] = node_id
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
        }
        items.append(item)
        return item

    def _stack_has_pending(self, stack: dict[str, Any]) -> bool:
        items = stack.get("items", [])
        if not isinstance(items, list):
            return False
        return any(
            isinstance(item, dict) and str(item.get("status") or "") == "pending_approval"
            for item in items
        )

    def _on_tool_stack_toggle_requested(self, stack_id: str) -> None:
        stack = self._find_tool_stack(stack_id)
        if stack is None:
            return
        if self._stack_has_pending(stack):
            stack["expanded"] = True
        else:
            stack["expanded"] = not bool(stack.get("expanded", False))
        self._render()

    def _render(self) -> None:
        # Any full render resets the page. We'll re-arm _page_loaded via loadFinished.
        self._page_loaded = False

        html = render_chat_html(
            self._messages,
            theme=self._theme,
            assistant_stream_index=self._assistant_stream_index if self._assistant_stream_active else None,
        )
        self._view.setHtml(html, QUrl("file:///"))
