from __future__ import annotations

from typing import List, Dict, Optional
from html import escape
import re
import json

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

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
});
</script>
</head>

<body>
<div class="chat-container">
{messages_html}
</div>
</body>
</html>
"""


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


def render_chat_html(
    messages: List[Dict[str, str]],
    theme: Optional[Dict[str, str]] = None,
    assistant_stream_index: int | None = None,
) -> str:
    parts: List[str] = []

    for i, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        meta = msg.get("meta")

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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._view = QWebEngineView(self)
        self._messages: list[dict[str, str]] = []
        self._theme: dict[str, str] | None = None

        # Streaming state (UI is turn-locked, so only one assistant stream can be active).
        self._assistant_stream_active: bool = False
        self._assistant_stream_index: int | None = None

        # If deltas arrive before the page finishes loading after begin_assistant_stream(),
        # buffer them and flush once loadFinished fires.
        self._page_loaded: bool = False
        self._pending_stream_deltas: list[str] = []

        self._view.loadFinished.connect(self._on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._render()

    def add_turn(self, role: str, text: str, meta: str | None = None) -> None:
        msg: dict[str, str] = {"role": role, "content": text}
        if meta:
            msg["meta"] = meta
        self._messages.append(msg)

        # Any explicit add_turn finalizes any in-progress assistant stream.
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._pending_stream_deltas.clear()

        # Force immediate render for discrete turns.
        self._render()

    # --- Streaming assistant API -------------------------------------------------

    def begin_assistant_stream(self) -> None:
        """Create an empty assistant bubble and prepare to append streaming deltas."""
        msg: dict[str, str] = {"role": "you", "content": ""}
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

    def _render(self) -> None:
        # Any full render resets the page. We'll re-arm _page_loaded via loadFinished.
        self._page_loaded = False

        html = render_chat_html(
            self._messages,
            theme=self._theme,
            assistant_stream_index=self._assistant_stream_index if self._assistant_stream_active else None,
        )
        self._view.setHtml(html, QUrl("file:///"))

