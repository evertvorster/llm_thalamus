"""AttachmentBar — QFrame containing ChatInput + attachment sidebar.

┌──────────────────────────────────────────┐
│ ┌────────────QPlainTextEdit─────────┬──┐ │
│ │ [file: plan.md]                   │📎│ │
│ │ [file: diagram.png]               │🖼│ │
│ │                                   │ ✕│ │
│ └───────────────────────────────────┴──┘ │
└──────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class AttachmentSidebar(QtWidgets.QScrollArea):
    """Right-side column showing attached files with delete buttons."""

    removeRequested = QtCore.Signal(int)  # index of attachment to remove

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setStyleSheet(
            "AttachmentSidebar { border: none; background: transparent; }"
        )

        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._items: list[dict] = []  # [{name, path, icon}]

        # Start collapsed
        self.setFixedWidth(0)
        self.hide()

    def add_file(self, name: str, path: str) -> int:
        """Add a file to the sidebar. Returns its index."""
        idx = len(self._items)

        # Determine icon
        icon = self._icon_for_file(path, name)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        icon_label = QtWidgets.QLabel()
        pixmap = icon.pixmap(32, 32)
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(32, 32)
        row.addWidget(icon_label)

        name_label = QtWidgets.QLabel(name)
        name_label.setStyleSheet("color: #888; font-size: 8pt;")
        name_label.setMaximumWidth(60)
        name_label.setToolTip(path)
        row.addWidget(name_label)

        del_btn = QtWidgets.QPushButton("\u2715")
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet(
            "QPushButton { border: none; color: #888; font-size: 10px; }"
            "QPushButton:hover { color: #f44; }"
        )
        del_btn.clicked.connect(lambda checked, i=idx: self.removeRequested.emit(i))
        row.addWidget(del_btn)

        self._items.append({"name": name, "path": path, "icon": icon})

        # Insert before the stretch
        item_widget = QtWidgets.QWidget()
        item_widget.setLayout(row)
        self._layout.insertWidget(self._layout.count() - 1, item_widget)

        self._update_visibility()
        return idx

    def remove_at(self, index: int) -> None:
        """Remove the item at *index*."""
        if 0 <= index < len(self._items):
            # Remove the widget from layout
            item = self._layout.takeAt(index)
            if item and item.widget():
                item.widget().deleteLater()
            self._items.pop(index)
            # Re-index remaining items
            self._rebind_buttons()
            self._update_visibility()

    def clear(self) -> None:
        """Remove all items."""
        for i in range(len(self._items) - 1, -1, -1):
            item = self._layout.takeAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._items.clear()
        self._update_visibility()

    def _rebind_buttons(self) -> None:
        """Reconnect delete buttons after removal shifts indices."""
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget():
                # Find the delete button (last child)
                btn = item.widget().findChild(QtWidgets.QPushButton)
                if btn:
                    try:
                        btn.clicked.disconnect()
                    except RuntimeError:
                        pass
                    btn.clicked.connect(
                        lambda checked, idx=i: self.removeRequested.emit(idx)
                    )

    def _update_visibility(self) -> None:
        if self._items:
            w = max(80, min(100, 40 + max(
                QtGui.QFontMetrics(QtWidgets.QApplication.font())
                .horizontalAdvance(n["name"]) for n in self._items
            )))
            self.setFixedWidth(w)
            self.show()
        else:
            self.setFixedWidth(0)
            self.hide()

    @staticmethod
    def _icon_for_file(path: str, name: str) -> QtGui.QIcon:
        """Return a suitable icon for the file."""
        # Try OS file icon first
        icon = QtWidgets.QFileIconProvider().icon(QtCore.QFileInfo(path))
        if not icon.isNull():
            return icon
        # Fallback: generic based on extension
        ext = Path(name).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            return QtWidgets.QFileIconProvider().icon(
                QtWidgets.QFileIconProvider.IconType.Image
            )
        return QtWidgets.QFileIconProvider().icon(
            QtWidgets.QFileIconProvider.IconType.File
        )


class AttachmentBar(QtWidgets.QFrame):
    """Container with ChatInput + attachment sidebar."""

    sendRequested = QtCore.Signal()
    textChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { border: 2px solid #888; border-radius: 4px; }")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from .widgets import ChatInput
        self.input = ChatInput()
        self.input.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.input.setStyleSheet("QPlainTextEdit { border: none; }")
        layout.addWidget(self.input, 1)

        self.sidebar = AttachmentSidebar()
        layout.addWidget(self.sidebar)

        # Relay signals
        self.input.sendRequested.connect(self.sendRequested)
        self.input.textChanged.connect(self.textChanged)

        # Wire sidebar remove → delete [file: ...] from text
        self.sidebar.removeRequested.connect(self._on_remove_attachment)

    # -- relay text API --------------------------------------------

    def toPlainText(self) -> str:
        return self.input.toPlainText()

    def clear(self) -> None:
        self.input.clear()
        self.sidebar.clear()

    def setPlaceholderText(self, text: str) -> None:
        self.input.setPlaceholderText(text)

    def textCursor(self) -> QtGui.QTextCursor:
        return self.input.textCursor()

    def setTextCursor(self, cursor: QtGui.QTextCursor) -> None:
        self.input.setTextCursor(cursor)

    def set_thinking_border_color(self, level: str) -> None:
        colors = {
            "off": "#888", "minimal": "#4caf50", "low": "#2196f3",
            "medium": "#ff9800", "high": "#f44336", "xhigh": "#9c27b0",
        }
        color = colors.get(level, "#888")
        self.setStyleSheet(
            f"QFrame {{ border: 2px solid {color}; border-radius: 4px; }}"
        )

    # -- attachment management -----------------------------------

    def add_dropped_file(self, path: str) -> None:
        """Handle a dropped file: add sidebar icon + insert [file: ...] in text."""
        name = QtCore.QFileInfo(path).fileName()
        self.sidebar.add_file(name, path)
        self.input.insertPlainText(f"[file: {name}]")

    def _on_remove_attachment(self, index: int) -> None:
        """Sidebar delete clicked — remove icon and matching [file: ...] text."""
        if 0 <= index < len(self.sidebar._items):
            name = self.sidebar._items[index]["name"]
            self.sidebar.remove_at(index)
            # Remove one matching [file: name] from text
            token = f"[file: {name}]"
            text = self.input.toPlainText()
            pos = text.find(token)
            if pos >= 0:
                cursor = self.input.textCursor()
                cursor.setPosition(pos)
                cursor.movePosition(
                    QtGui.QTextCursor.MoveOperation.Right,
                    QtGui.QTextCursor.MoveMode.KeepAnchor,
                    len(token),
                )
                cursor.removeSelectedText()
