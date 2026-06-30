"""Shared UI theme constants."""

from __future__ import annotations

# Border colors for each thinking level.
# Used by ChatInput and AttachmentBar to indicate the current
# reasoning effort level.
THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#1a1a2e",
        "text": "#e0e0e0",
        "bubble_user": "#2d2d44",
        "bubble_assistant": "#252535",
        "meta_text": "#888888",
        "border": "#444444",
    },
    "light": {
        "bg": "#f5f5f7",
        "text": "#000000",
        "bubble_user": "#e3f2fd",
        "bubble_assistant": "#ffffff",
        "meta_text": "#666666",
        "border": "#cccccc",
    },
}


THINKING_COLORS: dict[str, str] = {
    "off": "#888888",
    "minimal": "#4caf50",
    "low": "#2196f3",
    "medium": "#ff9800",
    "high": "#f44336",
    "xhigh": "#9c27b0",
}
