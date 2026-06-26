"""CommandPalette — slash-command autocomplete popup for the chat input."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class _CommandPopup(QtWidgets.QFrame):
    """Frameless popup list positioned above the chat input."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setStyleSheet(
            "_CommandPopup { background: #2d2d30; border: 1px solid #555; border-radius: 4px; }"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._list = QtWidgets.QListWidget()
        self._list.setStyleSheet(
            "QListWidget {"
            "  background: #2d2d30; color: #ddd; border: none;"
            "  font-size: 10pt; outline: none; padding: 2px 0;"
            "}"
            "QListWidget::item { padding: 3px 10px; }"
            "QListWidget::item:selected { background: #0e639c; color: white; }"
            "QListWidget::item:hover { background: #3e3e42; }"
        )
        self._list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self._list)

        self._all_items: list[tuple[str, str]] = []  # (name, description)
        self._filter: str = ""

    def set_items(self, items: list[tuple[str, str]]) -> None:
        """Replace the full command list.  Each entry is (name, description)."""
        self._all_items = items
        self._apply_filter()

    def set_filter(self, text: str) -> None:
        """Filter visible items by prefix‑matching *text*."""
        self._filter = text.lower()
        self._apply_filter()

    def select_first(self) -> None:
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def select_previous(self) -> None:
        row = self._list.currentRow()
        if row > 0:
            self._list.setCurrentRow(row - 1)

    def select_next(self) -> None:
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            self._list.setCurrentRow(row + 1)

    def current_command(self) -> str | None:
        item = self._list.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def visible_count(self) -> int:
        return self._list.count()

    # ── internals ──────────────────────────────────────────────

    def _apply_filter(self) -> None:
        self._list.clear()
        for name, desc in self._all_items:
            if self._filter and self._filter not in name.lower():
                continue
            if desc:
                label = f"/{name}  —  {desc[:50]}" if len(desc) > 50 else f"/{name}  —  {desc}"
            else:
                label = f"/{name}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)


class CommandPalette(QtCore.QObject):
    """Manages the slash‑command popup lifecycle.

    Attach to a :class:`ChatInput` and a :class:`PiRPCBridge` via
    :meth:`attach` and :meth:`set_dynamic_commands`.  The palette handles
    showing / hiding / filtering / keyboard navigation internally.
    """

    # Emitted when a command that needs parent-level handling is selected
    # (e.g. /name, /model, anything with arguments or UI requirements).
    command_requested = QtCore.Signal(str, str)  # (command_name, remaining_text)

    @property
    def is_visible(self) -> bool:
        """True while the popup is showing."""
        return self._visible

    # Hard‑coded built‑in RPC commands that can be sent directly.
    _BUILTINS: dict[str, tuple[str, str | None]] = {
        "clone":   ("Duplicate current branch", "clone"),
        "compact": ("Compact context", "compact"),
        "reload":  ("Reload extensions, skills, and config", None),
    }

    # Commands dispatched via RPC but require UI interaction first.
    _UI_COMMANDS: set[str] = {"name", "export", "model", "scoped-models", "resume", "new", "session"}

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._bridge: object | None = None           # PiRPCBridge
        self._input: QtWidgets.QPlainTextEdit | None = None
        self._popup: _CommandPopup | None = None
        self._dynamic_commands: list[tuple[str, str]] = []  # from get_commands
        self._visible: bool = False
        self._max_width: int = 400

        # Defer creation until we know the parent widget.
        self._popup_created: bool = False

    def attach(
        self,
        bridge: object,           # PiRPCBridge
        input_widget: QtWidgets.QPlainTextEdit,
    ) -> None:
        """Wire the palette to the bridge and chat input."""
        self._bridge = bridge
        self._input = input_widget
        self._input.textChanged.connect(self._on_text_changed)
        self._input.installEventFilter(self)

    def set_dynamic_commands(self, commands: list[dict]) -> None:
        """Cache the ``get_commands`` response for populating the palette."""
        self._dynamic_commands.clear()
        for c in commands:
            name = c.get("name", "")
            desc = c.get("description", "")
            source = c.get("source", "")
            if source:
                desc = f"{desc}  [{source}]" if desc else f"[{source}]"
            self._dynamic_commands.append((name, desc))

    # ── private slots ────────────────────────────────────────────

    def _on_text_changed(self) -> None:
        text = self._input.toPlainText() if self._input else ""
        is_slash = text.startswith("/") and not self._input.textCursor().hasSelection()

        if is_slash and not self._visible:
            self._show()
        elif not is_slash and self._visible:
            self._hide()

        if self._visible:
            after = text[1:]  # text after the /
            self._popup.set_filter(after)
            self._popup.select_first()

    # ── popup management ─────────────────────────────────────────

    def _show(self) -> None:
        self._ensure_popup()
        self._popup.set_items(self._all_commands())

        # Position as a child widget (not a Popup window), so use
        # parent-relative coordinates.
        input_pos = self._input.mapTo(
            self._input.window(),
            self._input.rect().topLeft(),
        )
        height = min(12 * 22, 240)  # cap at ~12 items
        self._popup.setGeometry(input_pos.x(), input_pos.y() + 2, self._max_width, height)
        self._popup.raise_()
        self._popup.show()
        self._popup.set_filter(self._input.toPlainText()[1:])
        self._popup.select_first()
        self._visible = True

        # Safety net: restore keyboard focus to the input in case the widget
        # manager briefly routed it elsewhere.
        self._input.setFocus()

    def _hide(self) -> None:
        if self._popup is not None:
            self._popup.hide()
        self._visible = False

    def _ensure_popup(self) -> None:
        if self._popup_created:
            return
        self._popup = _CommandPopup(self._input.window())
        self._popup._list.itemClicked.connect(self._on_popup_item_clicked)
        self._popup_created = True

    # ── command list ─────────────────────────────────────────────

    def _all_commands(self) -> list[tuple[str, str]]:
        """Return the merged (builtin + dynamic) command list."""
        items: list[tuple[str, str]] = []
        for name, (desc, _rpc) in self._BUILTINS.items():
            items.append((name, desc))
        for name in self._UI_COMMANDS:
            # Only add if not already covered by builtins.
            if name not in self._BUILTINS:
                items.append((name, ""))
        items.extend(self._dynamic_commands)
        items.sort(key=lambda x: x[0])
        return items

    # ── keyboard navigation (event filter on ChatInput) ────────

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is not self._input or not self._visible:
            return False

        if event.type() == QtCore.QEvent.Type.KeyPress:
            ke = event

            if ke.key() == QtCore.Qt.Key_Up:
                self._popup.select_previous()
                return True

            if ke.key() == QtCore.Qt.Key_Down:
                self._popup.select_next()
                return True

            if ke.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Tab):
                name = self._popup.current_command()
                if name is not None:
                    self._dispatch(name)
                return True

            if ke.key() == QtCore.Qt.Key_Escape:
                self._hide()
                self._input.clear()
                return True

        return False

    def _on_popup_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        name = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if name:
            self._dispatch(name)

    # ── dispatch ────────────────────────────────────────────────

    def _dispatch(self, name: str) -> None:
        """Route the selected command to the bridge or parent."""
        self._hide()

        # Builtin: simple RPC, or prompt-based when no RPC command exists.
        if name in self._BUILTINS:
            _desc, rpc_cmd = self._BUILTINS[name]
            if rpc_cmd:
                self._bridge.send_command({"type": rpc_cmd})
            else:
                self._bridge.send_command(
                    {"type": "prompt", "message": "/" + name}
                )
            self._input.clear()
            return

        # UI‑requiring commands: delegate to parent.
        if name in self._UI_COMMANDS:
            text = self._input.toPlainText()
            after = text[len("/" + name):].strip()
            self._input.clear()
            self.command_requested.emit(name, after)
            return

        # Dynamic command: send as prompt.
        text = self._input.toPlainText().strip()
        self._input.clear()
        self._bridge.send_command(
            {"type": "prompt", "message": text}
        )
