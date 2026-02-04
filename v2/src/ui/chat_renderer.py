from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser


class ChatRenderer(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setOpenExternalLinks(True)

    def add_turn(self, role: str, text: str):
        self.append(f"<b>{role}:</b> {text}<br>")
