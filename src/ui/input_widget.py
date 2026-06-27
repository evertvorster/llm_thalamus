"""InputWebView — a contentEditable QWebEngineView replacing ChatInput.

Provides the same external API as the old ChatInput (QPlainTextEdit):
  - sendRequested signal
  - textChanged signal (no argument — use .text property)
  - clear()
  - get_text(callback) — async, replaces toPlainText()
  - set_thinking_border_color(level)
"""

from __future__ import annotations

import json
from typing import Callable
from urllib.parse import unquote

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

from .input_page import input_html_template

_THINKING_COLORS: dict[str, str] = {
    "off": "#888888", "minimal": "#4caf50", "low": "#2196f3",
    "medium": "#ff9800", "high": "#f44336", "xhigh": "#9c27b0",
}


class InputPage(QWebEnginePage):
    """Intercepts ``thalamus://`` URLs from JavaScript and emits signals."""

    sendRequested = Signal()
    textChanged = Signal()
    paletteAction = Signal(str)  # "tab" | "escape" | "up" | "down"

    def __init__(self, parent: QWebEngineView) -> None:
        super().__init__(parent)
        self._text: str = ""

    @property
    def text(self) -> str:
        return self._text

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() != "thalamus":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        host = url.host()

        if host == "send":
            self.sendRequested.emit()
        elif host == "text":
            self._text = unquote(url.path().lstrip("/"))
            self.textChanged.emit()
        elif host in ("tab", "escape", "up", "down"):
            self.paletteAction.emit(host)

        return False  # cancel navigation


class InputWebView(QWebEngineView):
    """ContentEditable input widget backed by Qt WebEngine."""

    sendRequested = Signal()
    textChanged = Signal()
    paletteAction = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = InputPage(self)
        self.setPage(self._page)

        # Relay page signals
        self._page.sendRequested.connect(self.sendRequested)
        self._page.textChanged.connect(self.textChanged)
        self._page.paletteAction.connect(self.paletteAction)

        self._theme: str = "dark"
        self._load_page()

        self.setStyleSheet(
            "QWebEngineView { border: 2px solid #888; border-radius: 4px; }"
        )
        self.setMinimumHeight(60)

        # Restore saved zoom
        _zs = QSettings("llm-thalamus", "llm-thalamus")
        _zv = _zs.value("input/zoom")
        if _zv is not None:
            try:
                self.setZoomFactor(max(0.3, min(3.0, float(_zv))))
            except (ValueError, TypeError):
                pass

    # ── public API ──────────────────────────────────────

    def clear(self) -> None:
        self.page().runJavaScript("clearInput()")

    def get_text(self, callback: Callable[[dict], None]) -> None:
        """Async: callback receives ``{"text": str, "images": [...]}``."""
        def _handle(raw: str | None) -> None:
            if raw:
                try:
                    result = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result = {"text": "", "images": []}
            else:
                result = {"text": "", "images": []}
            callback(result)

        self.page().runJavaScript("getInputContent()", _handle)

    @property
    def text(self) -> str:
        return self._page.text

    def set_thinking_border_color(self, level: str) -> None:
        color = _THINKING_COLORS.get(level, "#888888")
        self.setStyleSheet(
            f"QWebEngineView {{ border: 2px solid {color}; border-radius: 4px; }}"
        )

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.page().runJavaScript(
            f"document.body.setAttribute('data-theme', '{theme}')"
        )

    def set_popup_visible(self, visible: bool) -> None:
        val = "true" if visible else "false"
        self.page().runJavaScript(f"window._popupVisible = {val}")

    def persist_zoom(self) -> None:
        s = QSettings("llm-thalamus", "llm-thalamus")
        s.setValue("input/zoom", self.zoomFactor())
        s.sync()

    def insert_text(self, text: str) -> None:
        escaped = json.dumps(text)
        self.page().runJavaScript(
            f"document.execCommand('insertText', false, {escaped})"
        )

    # ── internal ────────────────────────────────────────

    def _load_page(self) -> None:
        html = input_html_template(theme=self._theme)
        self.setHtml(html, QUrl("file:///"))
