from __future__ import annotations

from typing import List, Dict, Optional
from html import escape
import re

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

from markdown_it import MarkdownIt

# Single shared Markdown parser instance
_md = MarkdownIt("commonmark", {"html": True})


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

<!-- KaTeX for LaTeX rendering (system-installed, Arch katex package) -->
<link rel="stylesheet"
      href="file:///usr/lib/node_modules/katex/dist/katex.min.css">
<script defer
        src="file:///usr/lib/node_modules/katex/dist/katex.min.js"></script>
<script defer
        src="file:///usr/lib/node_modules/katex/dist/contrib/auto-render.min.js"></script>

<!-- highlight.js syntax highlighting (system node module) -->
<link rel="stylesheet"
      href="file:///usr/lib/node_modules/@highlightjs/cdn-assets/styles/github-dark.min.css">
<script src="file:///usr/lib/node_modules/@highlightjs/cdn-assets/highlight.min.js"></script>

<script>
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

// Simple KaTeX auto-render for $...$ and $$...$$
function renderMath() {
    if (typeof renderMathInElement === "undefined") {
        return;
    }
    renderMathInElement(document.body, {
        delimiters: [
            {left: "$$", right: "$$", display: true},
            {left: "$", right: "$", display: false}
        ]
    });
}

document.addEventListener("DOMContentLoaded", function() {
    prettifyJsonBlocks();
    highlightCodeBlocks();
    enhanceCodeBlocks();
    renderMath();

    // auto-scroll to bottom
    window.scrollTo(0, document.body.scrollHeight);
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


def render_chat_html(messages: List[Dict[str, str]], theme: Optional[Dict[str, str]] = None) -> str:
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

        self._render()

    # --- Streaming assistant API -------------------------------------------------

    def begin_assistant_stream(self) -> None:
        """Create an empty assistant bubble and prepare to append streaming deltas."""
        msg: dict[str, str] = {"role": "you", "content": ""}
        self._messages.append(msg)
        self._assistant_stream_active = True
        self._assistant_stream_index = len(self._messages) - 1
        self._render()

    def append_assistant_delta(self, text: str) -> None:
        """Append streaming text to the current assistant bubble."""
        if not self._assistant_stream_active:
            return
        if self._assistant_stream_index is None:
            return
        if not text:
            return

        self._messages[self._assistant_stream_index]["content"] += text
        self._render()

    def end_assistant_stream(self) -> None:
        """Finalize assistant streaming."""
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._render()

    # ---------------------------------------------------------------------------

    def set_theme(self, theme: dict[str, str] | None) -> None:
        self._theme = theme
        self._render()

    def clear(self) -> None:
        self._messages.clear()
        self._assistant_stream_active = False
        self._assistant_stream_index = None
        self._render()

    def _render(self) -> None:
        html = render_chat_html(self._messages, theme=self._theme)
        # baseUrl left as default; template uses absolute file:/// paths for assets
        self._view.setHtml(html, QUrl("file:///"))
