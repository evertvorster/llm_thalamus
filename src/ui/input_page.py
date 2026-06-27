"""HTML template, CSS, and JavaScript for the contentEditable input widget."""

from __future__ import annotations

_STYLE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
    height: 100%;
    overflow: hidden;
}

body {
    font-family: "Courier New", monospace;
    font-size: 14px;
    line-height: 1.4;
    --bg: #1e1e1e;
    --text: #d4d4d4;
    --placeholder: #888;
    --border: #444;
    --thumb-bg: #2d2d30;
}

.container {
    display: flex;
    height: 100%;
    overflow: hidden;
}

/* ── text area ──────────────────────────────────── */

.input-text {
    flex: 1;
    padding: 8px;
    outline: none;
    white-space: pre-wrap;
    word-wrap: break-word;
    border: none;
    background: transparent;
    color: inherit;
    align-self: flex-start;
    position: relative;
}

/* Placeholder — absolutely positioned, opacity toggle (no reflow) */
.input-text .placeholder-label {
    position: absolute;
    left: 8px; top: 8px;
    color: var(--placeholder);
    pointer-events: none;
    user-select: none;
}
.input-text:not(.placeholder) .placeholder-label { opacity: 0; }

/* Chromium contentEditable loses caret inheritance — force everywhere */
*, *::before, *::after {
    caret-color: var(--text) !important;
}

/* ── attachment column ──────────────────────────── */

.attachments {
    width: 0;
    overflow-y: auto;
    overflow-x: hidden;
    background: var(--thumb-bg);
    border-left: 1px solid var(--border);
    flex-shrink: 0;
    transition: width 0.15s ease;
}

.attachments.has-items { width: 80px; }

.attachment-item {
    padding: 6px;
    text-align: center;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
    position: relative;
}

.attachment-item:hover { background: rgba(255, 255, 255, 0.08); }

.attachment-thumb {
    width: 48px; height: 48px;
    object-fit: cover; border-radius: 4px;
    display: block; margin: 0 auto 2px;
}

.attachment-filename {
    font-size: 9px; color: var(--placeholder);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 68px;
}

.attachment-delete {
    position: absolute; top: 2px; right: 2px;
    width: 16px; height: 16px; padding: 0;
    border: none; border-radius: 50%;
    background: rgba(0, 0, 0, 0.6); color: #fff;
    font-size: 10px; line-height: 16px; cursor: pointer; display: none;
}

.attachment-item:hover .attachment-delete { display: block; }

/* ── Thinking level border (on body, not widget) ── */
body[data-thinking="off"]      { border: 2px solid #888888; }
body[data-thinking="minimal"]  { border: 2px solid #4caf50; }
body[data-thinking="low"]      { border: 2px solid #2196f3; }
body[data-thinking="medium"]   { border: 2px solid #ff9800; }
body[data-thinking="high"]     { border: 2px solid #f44336; }
body[data-thinking="xhigh"]    { border: 2px solid #9c27b0; }

/* ── Themes ─────────────────────────────────────── */
body[data-theme="light"] {
    --bg: #ffffff; --text: #000000; --placeholder: #999;
    --border: #ccc; --thumb-bg: #f0f0f0;
}
body[data-theme="dark"] {
    --bg: #1e1e1e; --text: #d4d4d4; --placeholder: #888;
    --border: #444; --thumb-bg: #2d2d30;
}
"""

_JS_RUNTIME = """
(function() {
    'use strict';
    var textEl = document.querySelector('.input-text');
    var attachEl = document.getElementById('attachment-column');

    function _bridge(url) { location.href = url; }

    // ── placeholder toggle ─────────────────────────
    function _placeholder() {
        textEl.classList.toggle('placeholder', !textEl.textContent.trim());
    }

    // ── text change batching ───────────────────────
    var _batchTimer = 0;
    textEl.addEventListener('input', function() {
        _placeholder();
        if (!_batchTimer) {
            _batchTimer = setTimeout(function() {
                _batchTimer = 0;
                _bridge('thalamus://text/' +
                    encodeURIComponent(textEl.textContent));
            }, 50);
        }
    });

    // ── keyboard handling ─────────────────────────
    textEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            _bridge(window._popupVisible ? 'thalamus://tab'
                                         : 'thalamus://send');
            return;
        }
        if (e.key === 'Tab') {
            e.preventDefault();
            _bridge('thalamus://tab');
            return;
        }
        if (e.key === 'Escape') {
            _bridge('thalamus://escape');
            return;
        }
        if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') &&
            window._popupVisible) {
            e.preventDefault();
            _bridge('thalamus://' + (e.key === 'ArrowUp' ? 'up' : 'down'));
        }
    });

    // ── paste (strip formatting) ──────────────────
    textEl.addEventListener('paste', function(e) {
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData)
            .getData('text/plain');
        if (text) {
            document.execCommand('insertText', false, text);
        }
    });

    // ── public API ─────────────────────────────────
    window.getInputContent = function() {
        var text = textEl ? textEl.textContent : '';
        var images = [];
        var items = attachEl.querySelectorAll('.attachment-item');
        for (var i = 0; i < items.length; i++) {
            var d = items[i].getAttribute('data-image-data');
            var m = items[i].getAttribute('data-mime');
            if (d && m) images.push({data: d, mimeType: m});
        }
        return JSON.stringify({text: text, images: images});
    };

    window.clearInput = function() {
        textEl.innerHTML = '';
        _placeholder();
    };

    window.getRawText = function() {
        return textEl ? textEl.textContent : '';
    };
})();
"""

def input_html_template(theme: str = "dark") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>{_STYLE_CSS}</style>
</head>
<body data-theme="{theme}" data-thinking="off">
<div class="container">
    <div class="input-text" contenteditable="true"
         data-placeholder="Type a message\u2026">
        <span class="placeholder-label" contenteditable="false">Type a message\u2026</span>
    </div>
    <div class="attachments" id="attachment-column"></div>
</div>
<script>{_JS_RUNTIME}</script>
</body></html>"""
