"""CommandPalette — slash-command dialog for the chat input."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QTimer


class CommandDialog(QtWidgets.QDialog):
    """Searchable command palette.

    Shows a search field and a filtered list of commands.  The user
    types to filter, navigates with arrows, and selects with Enter
    or double-click.

    Use :meth:`selected_name` after exec() to get the chosen command.
    """

    def __init__(
        self,
        commands: list[tuple[str, str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.resize(380, 300)

        self._commands = commands
        self._selected_name: str | None = None

        layout = QtWidgets.QVBoxLayout(self)

        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("Type to filter commands…")
        layout.addWidget(self._search)

        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list)

        self._populate("")
        self._search.textChanged.connect(self._on_search)
        self._list.itemDoubleClicked.connect(self._accept_selected)
        self._search.installEventFilter(self)

    # ── public accessors ────────────────────────────────────────

    def selected_name(self) -> str | None:
        """Name of the command the user picked, or *None* if cancelled."""
        return self._selected_name

    # ── event filter (search field keyboard shortcuts) ──────────

    def eventFilter(
        self, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if obj is not self._search:
            return False
        if event.type() != QtCore.QEvent.Type.KeyPress:
            return False

        ke = event

        # Route Up/Down to the list widget.
        if ke.key() == QtCore.Qt.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
            return True

        if ke.key() == QtCore.Qt.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
            return True

        # Enter/Return selects the highlighted command.
        if ke.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._accept_selected()
            return True

        if ke.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return True

        return False

    # ── internals ──────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._populate(text)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _populate(self, filter_text: str) -> None:
        self._list.clear()
        ft = filter_text.lower()
        for name, desc in self._commands:
            if ft and ft not in name.lower():
                continue
            label = f"/{name}" + (f"  —  {desc}" if desc else "")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)

    def _accept_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self._selected_name = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.accept()


class CommandPalette(QtCore.QObject):
    """Slash-command palette that opens a :class:`CommandDialog` when
    ``/`` is typed first in the chat input.

    Call :meth:`attach` with the :class:`PiRPCBridge` and the chat input
    widget.  Call :meth:`set_dynamic_commands` with the commands reported
    by pi's ``get_commands`` RPC.

    When the user selects a command from the dialog, the palette either
    sends the RPC directly or emits :attr:`command_requested` for commands
    that need parent-level UI interaction.
    """

    # Emitted when a command needs parent-level handling
    # (e.g. /name, /model, anything with arguments or UI requirements).
    command_requested = QtCore.Signal(str, str)  # (command_name, remaining_text)

    # Hard‑coded built‑in RPC commands that can be sent directly.
    _BUILTINS: dict[str, tuple[str, str | None]] = {
        "clone": ("Duplicate current branch", "clone"),
    }

    # Commands dispatched via RPC but require UI interaction first.
    _UI_COMMANDS: set[str] = {
        "name", "export", "model", "scoped-models",
        "resume", "new", "session", "tree", "compact",
        "copy", "import", "reload", "hotkeys", "quit", "settings",
    }

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._bridge: object | None = None
        self._input: QtWidgets.QPlainTextEdit | None = None
        self._dynamic_commands: list[tuple[str, str]] = []
        self._search_filter: str = ""

    def attach(
        self,
        bridge: object,
        input_widget: QtWidgets.QPlainTextEdit,
    ) -> None:
        """Wire the palette to the bridge and chat input."""
        self._bridge = bridge
        self._input = input_widget
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_text_changed)

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

    # ── key interception ────────────────────────────────────────

    def _on_text_changed(self) -> None:
        """Fallback: if a lone ``/`` lands in the input, consume and open dialog."""
        if self._input and self._input.toPlainText() == "/":
            self._input.clear()
            QTimer.singleShot(0, self.open_dialog)

    def eventFilter(
        self, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Catch ``/`` before it reaches the input and open the command dialog."""
        if obj is not self._input:
            return False
        if event.type() == QtCore.QEvent.Type.KeyPress:
            ke = event
            if not self._input.toPlainText() and (
                ke.key() == QtCore.Qt.Key_Slash or ke.text() == "/"
            ):
                QTimer.singleShot(0, self.open_dialog)
                return True
        return False

    # ── command dialog ──────────────────────────────────────────

    def open_dialog(self) -> None:
        """Open the command palette dialog and dispatch the selection."""
        dlg = CommandDialog(self._all_commands(), self._input.window())
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            self._input.setFocus()
            return

        name = dlg.selected_name()
        if name is None:
            self._input.setFocus()
            return

        self._dispatch_selected(name)
        self._input.setFocus()

    # ── command list ─────────────────────────────────────────────

    def _all_commands(self) -> list[tuple[str, str]]:
        """Return the merged (builtin + UI + dynamic) command list."""
        items: list[tuple[str, str]] = []
        for name, (desc, _rpc) in self._BUILTINS.items():
            items.append((name, desc))
        for name in self._UI_COMMANDS:
            if name not in self._BUILTINS:
                items.append((name, ""))
        items.extend(self._dynamic_commands)
        items.sort(key=lambda x: x[0])
        return items

    # ── dispatch ────────────────────────────────────────────────

    def _dispatch_selected(self, name: str) -> None:
        """Route the selected command to the bridge or parent."""
        # Builtin: simple RPC, or prompt-based when no RPC command exists.
        if name in self._BUILTINS:
            _desc, rpc_cmd = self._BUILTINS[name]
            if rpc_cmd:
                self._bridge.send_command({"type": rpc_cmd})
            else:
                self._bridge.send_command(
                    {"type": "prompt", "message": "/" + name}
                )
            return

        # UI‑requiring commands: delegate to parent.
        if name in self._UI_COMMANDS:
            self.command_requested.emit(name, "")
            return

        # Dynamic command: send as prompt.
        self._bridge.send_command(
            {"type": "prompt", "message": "/" + name}
        )

    # ── dispatch (via send path) ─────────────────────────────────

    def try_dispatch(self, text: str) -> bool:
        """Try to dispatch *text* as a slash command.

        Returns True if *text* was recognised as a known command and
        dispatched, False if it should be sent as a normal message.
        """
        text = text.strip()
        if not text.startswith("/"):
            return False

        parts = text[1:].split(None, 1)
        name = parts[0].lower() if parts else ""
        remaining = parts[1] if len(parts) > 1 else ""

        if not name:
            return False

        # Builtin commands.
        if name in self._BUILTINS:
            _desc, rpc_cmd = self._BUILTINS[name]
            if rpc_cmd:
                self._bridge.send_command({"type": rpc_cmd})
            else:
                self._bridge.send_command({"type": "prompt", "message": text})
            return True

        # UI commands (need parent coordination).
        if name in self._UI_COMMANDS:
            self.command_requested.emit(name, remaining)
            return True

        # Dynamic commands (from pi get_commands).
        for dyn_name, _ in self._dynamic_commands:
            if name == dyn_name.lower():
                self._bridge.send_command({"type": "prompt", "message": text})
                return True

        return False
