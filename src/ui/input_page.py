"""HTML template, CSS, and JavaScript for the contentEditable input widget.

This module provides the minimal HTML page used by ``InputWebView``.
All rendering logic (themes, thinking borders, placeholders) lives
here as HTML/CSS/JS, keeping the Python side thin.
"""

from __future__ import annotations

_STYLE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: "Courier New", monospace;
    font-size: 14px;
    line-height: 1.4;
    /* overflow: hidden removed — can clip caret rendering in Chromium */
    /* Default theme — overridden via data attributes at runtime */
    --bg: #1e1e1e;
    --text: #d4d4d4;
    --placeholder: #888;
    --border: #444;
    --thumb-bg: #2d2d30;
}

.container {
    display: flex;
    height: 100%;
    border: none;
    overflow: hidden;
}

/* ── text area ──────────────────────────────────── */

.input-text {
    flex: 1;
    padding: 8px;
    outline: none;
    white-space: pre-wrap;
    word-wrap: break-word;
    min-height: 100%;
    border: none;
    background: transparent;
    color: inherit;
    position: relative;
}

.input-text:focus {
    outline: none;
}

/* Placeholder via class toggle (avoids Chromium :empty bug that breaks caret) */
.input-text.placeholder::before {
    content: attr(data-placeholder);
    color: var(--placeholder);
    pointer-events: none;
    position: absolute;
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

.attachments.has-items {
    width: 80px;
}

.attachment-item {
    padding: 6px;
    text-align: center;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
    position: relative;
}

.attachment-item:hover {
    background: rgba(255, 255, 255, 0.08);
}

.attachment-thumb {
    width: 48px;
    height: 48px;
    object-fit: cover;
    border-radius: 4px;
    display: block;
    margin: 0 auto 2px;
}

.attachment-filename {
    font-size: 9px;
    color: var(--placeholder);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 68px;
}

.attachment-delete {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 16px;
    height: 16px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.6);
    color: #fff;
    font-size: 10px;
    line-height: 16px;
    cursor: pointer;
    display: none;
}

.attachment-item:hover .attachment-delete {
    display: block;
}

/* Force caret color on everything — Chromium contentEditable quirk */
html, body, .container, .input-text, .input-text * {
    caret-color: var(--text) !important;
}

/* ── Themes ─────────────────────────────────────── */

body[data-theme="light"] {
    --bg: #ffffff;
    --text: #000000;
    --placeholder: #999;
    --border: #ccc;
    --thumb-bg: #f0f0f0;
}

body[data-theme="dark"] {
    --bg: #1e1e1e;
    --text: #d4d4d4;
    --placeholder: #888;
    --border: #444;
    --thumb-bg: #2d2d30;
}

/* ── Thinking level border is applied via Qt stylesheet on the QWebEngineView widget.
     (No body border needed — avoids double borders.) */
"""


_JS_RUNTIME = """
(function() {
    'use strict';

    var textEl = document.querySelector('.input-text');
    var attachEl = document.getElementById('attachment-column');

    // ── helpers ───────────────────────────────────

    function _encode(s) {
        return encodeURIComponent(s);
    }

    function _bridge(url) {
        location.href = url;
    }

    // ── force caret visible (Chromium contentEditable quirk) ─

    function _fixCaret() {
        // Re-apply caret color via JS — CSS-only fixes don't always work
        // when Chromium creates nested editing host elements.
        var style = document.createElement('style');
        style.id = '_caret-fix';
        style.textContent = 'html, body, .container, .input-text, .input-text * {' +
            'caret-color: ' + getComputedStyle(document.body).getPropertyValue('--text').trim() + ' !important;' +
            '}';
        var old = document.getElementById('_caret-fix');
        if (old) old.remove();
        document.head.appendChild(style);
    }

    // Apply once on load (not on every input)
    _fixCaret();

    // ── placeholder toggle (avoids Chromium :empty bug) ──

    function _updatePlaceholder() {
        var hasText = textEl.textContent.trim().length > 0;
        textEl.classList.toggle('placeholder', !hasText);
    }

    textEl.addEventListener('input', _updatePlaceholder);
    textEl.addEventListener('blur', _updatePlaceholder);
    _updatePlaceholder();

    // ── text change batching ──────────────────────

    var _textDirty = false;

    textEl.addEventListener('input', function() {
        if (!_textDirty) {
            _textDirty = true;
            setTimeout(function() {
                _textDirty = false;
                _bridgeTextChanged();
            }, 50);
        }
    });

    function _bridgeTextChanged() {
        var text = textEl.textContent;
        _bridge('thalamus://text/' + _encode(text));
    }

    // ── keyboard handling ─────────────────────────
    // Attach to the contentEditable element itself (document-level listener
    // may not fire for contentEditable in Qt WebEngine/Chromium).

    textEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (window._popupVisible) {
                _bridge('thalamus://tab');
            } else {
                _bridge('thalamus://send');
            }
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
        if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && window._popupVisible) {
            e.preventDefault();
            _bridge('thalamus://' + (e.key === 'ArrowUp' ? 'up' : 'down'));
            return;
        }
    });

    // ── paste handler (strip formatting) ──────────

    document.addEventListener('paste', function(e) {
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain');
        if (text) {
            document.execCommand('insertText', false, text);
        }
    });

    // ── public API (called from Python via runJavaScript) ──

    window.getInputContent = function() {
        var text = textEl ? textEl.textContent : '';
        var images = [];
        var items = attachEl.querySelectorAll('.attachment-item');
        for (var i = 0; i < items.length; i++) {
            var data = items[i].getAttribute('data-image-data');
            var mime = items[i].getAttribute('data-mime');
            if (data && mime) {
                images.push({ data: data, mimeType: mime });
            }
        }
        // Return as JSON string — PySide6's runJavaScript cannot pass objects.
        return JSON.stringify({ text: text, images: images });
    };

    window.clearInput = function() {
        textEl.innerHTML = '';
        _updatePlaceholder();
    };

    window.getRawText = function() {
        return textEl ? textEl.textContent : '';
    };

    // ── attachment management (used in Step 2) ────

    window._attachments = [];

    window.addAttachment = function(dataUrl, mimeType, name) {
        var item = document.createElement('div');
        item.className = 'attachment-item';
        item.setAttribute('data-image-data', dataUrl.split(',')[1] || dataUrl);
        item.setAttribute('data-mime', mimeType);

        var img = document.createElement('img');
        img.className = 'attachment-thumb';
        img.src = dataUrl;
        item.appendChild(img);

        var label = document.createElement('div');
        label.className = 'attachment-filename';
        label.textContent = name;
        item.appendChild(label);

        var del = document.createElement('button');
        del.className = 'attachment-delete';
        del.textContent = '\\u2715';
        del.addEventListener('click', function(ev) {
            ev.stopPropagation();
            item.remove();
            _updateAttachColumn();
        });
        item.appendChild(del);

        item.addEventListener('click', function() {
            _bridge('thalamus://view-attachment/' + _encode(dataUrl) + '/' + _encode(mimeType));
        });

        attachEl.appendChild(item);
        _updateAttachColumn();
    };

    function _updateAttachColumn() {
        var has = attachEl.querySelectorAll('.attachment-item').length > 0;
        attachEl.classList.toggle('has-items', has);
    }

    window._popupVisible = false;

})();
"""


def input_html_template(theme: str = "dark", placeholder: str = "Type a message\u2026") -> str:
    """Return the full HTML page for the input widget."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>{_STYLE_CSS}</style>
</head>
<body data-theme="{theme}" data-thinking="off">
<div class="container">
    <div class="input-text" contenteditable="true" data-placeholder="{placeholder}"></div>
    <div class="attachments" id="attachment-column"></div>
</div>
<script>{_JS_RUNTIME}</script>
</body>
</html>"""
