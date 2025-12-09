from typing import List, Dict
from html import escape

from markdown_it import MarkdownIt

# Single shared Markdown parser instance
_md = MarkdownIt("commonmark", {"html": True})


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
body {
    margin: 0;
    padding: 8px;
    background-color: #f5f5f7;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
                 sans-serif;
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
    font-size: 14px;
    line-height: 1.4;
    word-wrap: break-word;
    white-space: normal;
}
.bubble.user {
    background: #e3f2fd; /* soft pastel blue */
    color: #000;
}
.bubble.assistant {
    background: #ffffff;
    color: #000;
}

.meta {
    font-size: 11px;
    color: #666;
    margin-bottom: 2px;
}

/* Code blocks */
pre.code-block {
    background: #1e1e1e;
    color: #f5f5f5;
    padding: 8px 10px;
    border-radius: 8px;
    font-family: "Fira Code", "JetBrains Mono", monospace;
    font-size: 13px;
    overflow-x: auto;
    white-space: pre;
    margin: 4px 0;

    /* NEW: make room + positioning for the copy button */
    position: relative;
    padding-top: 26px;
}
pre.code-block code {
    white-space: pre;
}

/* NEW: copy-code button */
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
</style>

<!-- KaTeX for LaTeX rendering (CDN) -->
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script>
function prettifyJsonBlocks() {
    // Find all fenced ```json blocks rendered by markdown-it
    var blocks = document.querySelectorAll('pre.code-block code.language-json');
    blocks.forEach(function(block) {
        try {
            var text = block.textContent;
            // Trim to avoid parse errors from stray whitespace
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

function applyRendering() {
    if (typeof renderMathInElement === "function") {
        renderMathInElement(document.body, {
            delimiters: [
                {left: "$$", right: "$$", display: true},
                {left: "$",  right: "$",  display: false},
                {left: "\\(", right: "\\)", display: false},
                {left: "\\[", right: "\\]", display: true}
            ]
        });
    }

    // Pretty-print JSON code blocks (```json fences)
    prettifyJsonBlocks();

    // NEW: add copy buttons to all code blocks
    enhanceCodeBlocks();

    // Scroll to bottom so the latest reply is visible
    window.scrollTo(0, document.body.scrollHeight);
}


function enhanceCodeBlocks() {
    var blocks = document.querySelectorAll('pre.code-block');
    blocks.forEach(function(pre) {
        // Avoid adding multiple buttons if the HTML is re-used
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
                    // fallback below if clipboard API fails
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
                // Older fallback
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


// Under Qt WebEngine, setHtml() loads a fresh document each time.
// The 'load' event is reliable, and we then defer actual rendering
// with a 0ms timeout so the DOM is fully painted.
window.addEventListener("load", function() {
    setTimeout(applyRendering, 0);
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


def _format_content_to_html(content: str) -> str:
    """Convert message text to HTML using markdown-it-py.

    - Standard Markdown (headings, lists, links, etc.) is supported.
    - Fenced code blocks (```lang) become <pre><code class="language-...">.
    - We post-process <pre><code> to add class="code-block" so existing
      dark code styling continues to apply.
    - LaTeX delimiters ($...$, $$...$$, \\(\\), \\[\\]) are left intact
      for KaTeX auto-rendering in the page template.
    """
    if not content:
        return ""

    # Let markdown-it handle Markdown → HTML
    html = _md.render(content)

    # Ensure our existing CSS for pre.code-block still applies by
    # adding class="code-block" to all <pre><code> blocks.
    html = html.replace("<pre><code", '<pre class="code-block"><code')

    return html


def render_chat_html(messages: List[Dict[str, str]]) -> str:
    """Render a list of chat messages to full HTML.

    Each message dict should have:
      - 'role': 'user' or 'assistant'
      - 'content': the message text
      - optional 'meta': short string shown above the bubble (e.g. 'previous session')
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "") or ""
        meta = msg.get("meta") or ""

        role_class = "user" if role == "user" else "assistant"
        bubble_class = role_class

        body_html = _format_content_to_html(content)

        meta_html = ""
        if meta:
            meta_html = f'<div class="meta">{escape(meta)}</div>'

        parts.append(
            f'<div class="message-row {role_class}">'
            f'  <div class="bubble {bubble_class}">'
            f'{meta_html}{body_html}'
            f'  </div>'
            f'</div>'
        )

    messages_html = "\n".join(parts)
    # Use simple replace so braces in CSS/JS aren't treated as format placeholders.
    return HTML_TEMPLATE.replace("{messages_html}", messages_html)
