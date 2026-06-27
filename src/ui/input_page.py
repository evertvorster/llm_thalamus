"""HTML template, CSS, and JavaScript for the contentEditable input widget."""

from __future__ import annotations

_STYLE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }

body {
    font-family: "Courier New", monospace;
    font-size: 14px;
    line-height: 1.4;
    --bg: #1e1e1e;
    --text: #d4d4d4;
    --thumb-bg: #2d2d30;
}

.editor {
    padding: 8px;
    outline: none;
    white-space: pre-wrap;
    word-wrap: break-word;
    border: none;
    background: transparent;
    color: inherit;
    height: 100%;
}

/* Thinking level border */
body[data-thinking="off"]      { border: 2px solid #888888; }
body[data-thinking="minimal"]  { border: 2px solid #4caf50; }
body[data-thinking="low"]      { border: 2px solid #2196f3; }
body[data-thinking="medium"]   { border: 2px solid #ff9800; }
body[data-thinking="high"]     { border: 2px solid #f44336; }
body[data-thinking="xhigh"]    { border: 2px solid #9c27b0; }

/* Themes */
body[data-theme="light"] { --bg: #ffffff; --text: #000000; --thumb-bg: #f0f0f0; }
"""

_JS_RUNTIME = """
(function() {
    'use strict';
    var el = document.querySelector('.editor');

    function _bridge(url) { location.href = url; }

    // ── text change batching ───────────────────────
    var _batchTimer = 0;
    el.addEventListener('input', function() {
        if (!_batchTimer) {
            _batchTimer = setTimeout(function() {
                _batchTimer = 0;
                _bridge('thalamus://text/' +
                    encodeURIComponent(el.textContent));
            }, 50);
        }
    });

    // ── keyboard handling ─────────────────────────
    el.addEventListener('keydown', function(e) {
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
    el.addEventListener('paste', function(e) {
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData)
            .getData('text/plain');
        if (text) document.execCommand('insertText', false, text);
    });

    // ── public API ─────────────────────────────────
    window.getInputContent = function() {
        return JSON.stringify({text: el.textContent || '', images: []});
    };
    window.clearInput = function() { el.innerHTML = ''; };
    window.getRawText = function() { return el.textContent || ''; };
})();
"""

def input_html_template(theme: str = "dark") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>{_STYLE_CSS}</style>
</head>
<body data-theme="{theme}" data-thinking="off">
<div class="editor" contenteditable="true"></div>
<script>{_JS_RUNTIME}</script>
</body></html>"""
