"""CommandPalette — slash-command dialog for the chat input."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class CommandDialog(QtWidgets.QDialog):
    """Searchable command palette.

    Shows a search field and a filtered list of commands.  The user
    types to filter, navigates with arrows, and selects with Enter
    or double-click.  Text after the command name is kept as its
    arguments, so `/ponytail lite` can be typed and run from here.

    After exec(), :meth:`selected_name` and :meth:`selected_args` give the
    command and whatever followed it.
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
        self._descriptions = dict(commands)
        self._selected_name: str | None = None
        self._selected_args: str = ""

        layout = QtWidgets.QVBoxLayout(self)

        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText("Command, then arguments — /ponytail lite")
        layout.addWidget(self._search)

        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list)

        # The highlighted command's description, in full.  Extensions put their
        # valid arguments here ("Set mode: lite|full|ultra|off"), and clipped
        # inside a list row it was unreadable.
        self._hint = QtWidgets.QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self._hint.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self._hint)

        # Enter runs the highlighted entry; this button does the same for people
        # who reach for the mouse.
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self._run_button = QtWidgets.QPushButton("Run")
        self._run_button.clicked.connect(self._accept_selected)
        buttons.addWidget(self._run_button)
        layout.addLayout(buttons)

        self._populate("")
        self._search.textChanged.connect(self._on_search)
        self._list.itemDoubleClicked.connect(self._accept_selected)
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._search.installEventFilter(self)

    # ── public accessors ────────────────────────────────────────

    def selected_name(self) -> str | None:
        """Name of the command the user picked, or *None* if cancelled."""
        return self._selected_name

    def selected_args(self) -> str:
        """Whatever the user typed after the command name."""
        return self._selected_args

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

    def _on_current_changed(self) -> None:
        """Show the highlighted command's description, arguments included."""
        item = self._list.currentItem()
        name = item.data(QtCore.Qt.ItemDataRole.UserRole) if item is not None else None
        self._hint.setText(self._descriptions.get(name, "") if name else "")

    def _populate(self, filter_text: str) -> None:
        self._list.clear()
        # Only the first word filters: the rest is the command's arguments, and
        # matching against it would empty the list the moment one is typed.
        head = filter_text.strip().split()[0].lower() if filter_text.strip() else ""
        for name, _desc in self._commands:
            if head and head not in name.lower():
                continue
            # The row is the name; the description lives in the hint below, where
            # it has room to wrap instead of being cut off.
            label = f"/{name}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)

    def _accept_selected(self) -> None:
        typed = self._search.text().strip()
        first, _, rest = typed.partition(" ")
        # A command typed in full outranks the highlighted row: the user said
        # which one they meant, and the arguments belong to it.
        item = self._list.currentItem()
        if first and any(first.lower() == n.lower() for n, _ in self._commands):
            name = first.lower()
            self._selected_args = rest.strip()
        elif item is not None:
            name = item.data(QtCore.Qt.ItemDataRole.UserRole)
            self._selected_args = ""
        else:
            return
        self._selected_name = name
        self.accept()


class CommandPalette(QtCore.QObject):
    """Slash-command palette, opened by its shortcut (Ctrl+/).

    Call :meth:`attach` with the :class:`PiRPCBridge` and the chat input
    widget.  Call :meth:`set_dynamic_commands` with the commands reported
    by pi's ``get_commands`` RPC.

    When the user selects a command from the dialog, the palette either
    sends the RPC directly, emits :attr:`command_requested` for commands
    that need parent-level UI interaction, or prefills the chat input so
    arguments can be typed.
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
        self._bar: object | None = None
        self._dynamic_commands: list[tuple[str, str]] = []
        self._search_filter: str = ""

    def attach(
        self,
        bridge: object,
        input_widget: QtWidgets.QPlainTextEdit,
        bar: object | None = None,
    ) -> None:
        """Wire the palette to the bridge and chat input.

        A leading ``/`` is typed normally: a command with arguments (e.g.
        ``/ponytail full``) has to reach pi as text, and swallowing the slash made
        that impossible. The palette opens from its shortcut instead.
        """
        self._bridge = bridge
        self._input = input_widget
        self._bar = bar

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

        self._dispatch_selected(name, dlg.selected_args())
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

    def _dispatch_selected(self, name: str, args: str = "") -> None:
        """Route the selected command to the bridge or parent.

        A command typed with arguments runs immediately — the user has already
        said what they want.  Without arguments it is prefilled into the input, so
        a level can be typed there rather than guessed at.
        """

        # Builtin: simple RPC, or prompt-based when no RPC command exists.
        if name in self._BUILTINS:
            _desc, rpc_cmd = self._BUILTINS[name]
            if rpc_cmd:
                self._bridge.send_command({"type": rpc_cmd})
            elif args:
                self._send("/" + name, args)
            else:
                self._prefill("/" + name)
            return

        # UI‑requiring commands: delegate to parent.
        if name in self._UI_COMMANDS:
            self.command_requested.emit(name, args)
            return

        # Dynamic command: with arguments, run it now; without, prefill.
        if args:
            self._send("/" + name, args)
        else:
            self._prefill("/" + name)

    def _send(self, command: str, args: str) -> None:
        """Send *command* with *args* to pi as a prompt."""
        self._bridge.send_command(
            {"type": "prompt", "message": f"{command} {args}".strip()}
        )

    def _prefill(self, text: str) -> None:
        """Put *text* in the chat input with a trailing space, cursor at the end.

        Attachments go with the text they belonged to: replacing one without the
        other leaves a chip claiming a file will be sent that no longer has a
        ``[file: ...]`` token to expand.
        """
        if self._input is None:
            return
        if self._bar is not None:
            self._bar.clear()
        self._input.setPlainText(text + " ")
        self._input.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self._input.setFocus()

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
