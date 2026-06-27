"""InputWebView — a contentEditable QWebEngineView replacing ChatInput.

Provides the same external API as the old ChatInput (QPlainTextEdit):
  - sendRequested signal
  - textChanged signal (str)
  - clear()
  - get_text(callback) — async, replaces toPlainText()
  - set_thinking_border_color(level)

Internal architecture:
  - HTML contentEditable page (see ``input_page.py``)
  - JS ``thalamus://`` URL bridge for keyboard/text events
  - Text mirror kept in sync for synchronous reads by the command palette
"""

from __future__ import annotations

import json
from typing import Callable
from urllib.parse import unquote

import json

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .input_page import input_html_template


# ── Thinking level colour map (kept in one place) ────────────────

_THINKING_COLORS: dict[str, str] = {
    "off": "#888888",
    "minimal": "#4caf50",
    "low": "#2196f3",
    "medium": "#ff9800",
    "high": "#f44336",
    "xhigh": "#9c27b0",
}


# ═══════════════════════════════════════════════════════════════════
#  Page — intercepts thalamus:// URL bridges
# ═══════════════════════════════════════════════════════════════════


class InputPage(QWebEnginePage):
    """Intercepts ``thalamus://`` URLs from JavaScript and emits signals."""

    # Emitted when the user presses Enter (without Shift) in the input.
    sendRequested = Signal()
    # Emitted when the input text changes (debounced JS → bridge).
    # (No argument — use ``text`` property for the current mirror value.)
    textChanged = Signal()
    # Emitted when Tab/Escape/Up/Down are pressed (for command palette).
    paletteAction = Signal(str)  # "tab" | "escape" | "up" | "down"
    # Emitted when an attachment thumbnail is clicked.
    viewAttachment = Signal(str, str)  # data_url, mime_type

    def __init__(self, parent: QWebEngineView) -> None:
        super().__init__(parent)
        self._text: str = ""  # synchronously accessible text mirror

    # -- public text access (mirror) -------------------------------

    @property
    def text(self) -> str:
        """Synchronously readable text mirror, updated by JS bridge."""
        return self._text

    # -- URL bridge intercept ---------------------------------------

    def acceptNavigationRequest(
        self, url: QUrl, nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if url.scheme() != "thalamus":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        host = url.host()

        if host == "send":
            self.sendRequested.emit()

        elif host == "text":
            # URL: thalamus://text/<encoded_text>
            raw = url.path().lstrip("/")
            decoded = unquote(raw)
            self._text = decoded
            self.textChanged.emit()

        elif host in ("tab", "escape", "up", "down"):
            self.paletteAction.emit(host)

        elif host == "view-attachment":
            # URL: thalamus://view-attachment/<encoded_data_url>/<mime>
            parts = url.path().lstrip("/").split("/", 1)
            if len(parts) == 2:
                data_url = unquote(parts[0])
                mime = unquote(parts[1])
                self.viewAttachment.emit(data_url, mime)

        return False  # Cancel navigation — the page stays as-is


# ═══════════════════════════════════════════════════════════════════
#  WebView — the widget used in place of ChatInput
# ═══════════════════════════════════════════════════════════════════


class InputWebView(QWebEngineView):
    """ContentEditable input widget backed by Qt WebEngine.

    Usage (drop-in for ``ChatInput``)::

        input_view = InputWebView()
        input_view.sendRequested.connect(self._on_send)
        input_view.textChanged.connect(self._on_input_text_changed)
        # ...
        # On send::
        input_view.get_text(lambda result: bridge.submit_message(result["text"]))
    """

    sendRequested = Signal()
    textChanged = Signal()
    paletteAction = Signal(str)  # "tab" | "escape" | "up" | "down"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = InputPage(self)
        self.setPage(self._page)

        # Relay page signals upward
        self._page.sendRequested.connect(self.sendRequested)
        self._page.textChanged.connect(self.textChanged)
        self._page.paletteAction.connect(self.paletteAction)

        # Set the initial HTML
        self._theme: str = "dark"
        self._load_page()

        # Style — border, not the full widget background
        self.setStyleSheet(
            "QWebEngineView { border: 2px solid #888; border-radius: 4px; }"
        )
        self.setMinimumHeight(60)

        # Restore saved zoom.
        _zs = QSettings("llm-thalamus", "llm-thalamus")
        _zv = _zs.value("input/zoom")
        if _zv is not None:
            try:
                self.setZoomFactor(max(0.3, min(3.0, float(_zv))))
            except (ValueError, TypeError):
                pass

    def set_zoom(self, factor: float) -> None:
        self.setZoomFactor(factor)

    def persist_zoom(self) -> None:
        s = QSettings("llm-thalamus", "llm-thalamus")
        s.setValue("input/zoom", self.zoomFactor())
        s.sync()

    # -- public API (mirrors ChatInput) ----------------------------

    def clear(self) -> None:
        """Clear the input contents."""
        self.page().runJavaScript("clearInput()")

    def get_text(
        self, callback: Callable[[dict], None] | None = None
    ) -> None:
        """Asynchronously retrieve the full input content.

        *callback* receives ``{"text": str, "images": [{"data": str, "mimeType": str}]}``.
        """
        def _handle(raw: str | None) -> None:
            if raw:
                try:
                    result = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result = {"text": "", "images": []}
            else:
                result = {"text": "", "images": []}
            if callback:
                callback(result)

        self.page().runJavaScript(
            "getInputContent()",
            _handle,
        )

    def get_raw_text(self, callback: Callable[[str], None]) -> None:
        """Asynchronously retrieve just the plain text content."""
        self.page().runJavaScript(
            "getRawText()",
            callback,
        )

    @property
    def text(self) -> str:
        """Synchronously accessible text mirror (slightly stale — last debounced update)."""
        return self._page.text

    def set_thinking_border_color(self, level: str) -> None:
        """Update the input border colour to reflect thinking level."""
        color = _THINKING_COLORS.get(level, "#888888")
        self.setStyleSheet(
            f"QWebEngineView {{ border: 2px solid {color}; border-radius: 4px; }}"
        )
        # Also update the page's data-thinking attribute for the inner border
        self.page().runJavaScript(
            f"document.body.setAttribute('data-thinking', '{level}')"
        )

    def set_theme(self, theme: str) -> None:
        """Switch between ``"dark"`` and ``"light"`` theme."""
        self._theme = theme
        self.page().runJavaScript(
            f"document.body.setAttribute('data-theme', '{theme}')"
        )

    def set_popup_visible(self, visible: bool) -> None:
        """Tell the JS side whether the command palette popup is visible."""
        val = "true" if visible else "false"
        self.page().runJavaScript(f"window._popupVisible = {val}")

    def insert_text(self, text: str) -> None:
        """Insert plain text at the cursor position (used by STT transcription)."""
        import json
        escaped = json.dumps(text)
        self.page().runJavaScript(
            f"document.execCommand('insertText', false, {escaped})"
        )

    def focus_text(self) -> None:
        """Place focus into the contentEditable area."""
        self.setFocus()
        self.page().runJavaScript(
            "document.querySelector('.input-text').focus()"
        )

    # -- internals ------------------------------------------------

    def _load_page(self) -> None:
        html = input_html_template(theme=self._theme)
        self.setHtml(html, QUrl("file:///"))
