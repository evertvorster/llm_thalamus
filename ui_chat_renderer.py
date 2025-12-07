from typing import List, Dict
from html import escape

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
}
pre.code-block code {
    white-space: pre;
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
document.addEventListener("DOMContentLoaded", function() {
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
    // Scroll to bottom on load so the latest reply is visible
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


def _format_content_to_html(content: str) -> str:
    """Convert message text to HTML with basic markdown-style code fences.

    - Triple backtick blocks (``` or ```lang) are rendered as <pre><code>.
    - Inside code blocks we HTML-escape everything.
    - Outside code blocks we leave text mostly as-is so LaTeX & <img> tags work,
      and just convert newlines to <br>.
    """
    if not content:
        return ""

    lines = content.splitlines()
    parts: list[str] = []
    in_code = False
    code_lang = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            # Fence line: either open or close a code block
            fence = stripped.lstrip("`")
            lang = fence.strip()  # e.g. 'python', 'json'

            if not in_code:
                in_code = True
                code_lang = lang
                lang_class = f" language-{code_lang}" if code_lang else ""
                parts.append(f'<pre class="code-block"><code class="{lang_class}">')
            else:
                in_code = False
                code_lang = ""
                parts.append("</code></pre>")
            continue

        if in_code:
            parts.append(escape(line) + "\n")
        else:
            parts.append(line + "<br>\n")

    if in_code:
        parts.append("</code></pre>")

    return "".join(parts)


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
