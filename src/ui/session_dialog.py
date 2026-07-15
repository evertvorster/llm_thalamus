"""SessionDialog — non‑modal dialog embedding the session tree + actions."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.widgets import SessionListWidget


class SessionDialog(QtWidgets.QDialog):
    """Non‑modal session manager dialog.

    Embeds a :class:`SessionListWidget` with two labelled button groups:

    * **Current Session** — actions that apply to the active session
      regardless of tree selection (New, Reload, Import, Session Info).
    * **Selected Session** — actions that apply to whatever is highlighted
      in the tree, driven by a single :meth:`execute_action` dispatch.

    Signals match those of :class:`SessionListWidget` plus dialog‑level
    actions:
        * ``new_requested()``
        * ``new_session_with_cwd(str)`` — skips file picker
        * ``reload_requested()``
        * ``import_requested()``
        * ``session_info_requested()``
        * ``switch_requested(str)``
        * ``rename_requested(str, str)``
        * ``delete_requested(list)``
        * ``inspect_requested(str)``
    """

    new_requested = QtCore.Signal()
    new_session_with_cwd = QtCore.Signal(str)  # cwd path, skips file picker
    reload_requested = QtCore.Signal()
    import_requested = QtCore.Signal()
    session_info_requested = QtCore.Signal()

    # Forwarded from the embedded SessionListWidget.
    switch_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    delete_requested = QtCore.Signal(list)
    inspect_requested = QtCore.Signal(str)

    # ── style constants ────────────────────────────────────────────

    _GROUP_STYLE = (
        "QGroupBox { font-weight: bold; border: 1px solid #ccc;"
        "  border-radius: 4px; margin-top: 6px; padding-top: 12px; }"
        "QGroupBox::title { subcontrol-origin: margin;"
        "  subcontrol-position: top left; padding: 0 4px; }"
    )

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Session Manager")
        self.resize(620, 540)
        self.setModal(False)

        self._current_session_path: str | None = None
        self._selected_session_path: str | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(6)

        # ── session tree ───────────────────────────────────────
        self._tree = SessionListWidget()
        # Forward signals.
        self._tree.switch_requested.connect(self.switch_requested)
        self._tree.rename_requested.connect(self.rename_requested)
        self._tree.delete_requested.connect(self.delete_requested)
        self._tree.inspect_requested.connect(self.inspect_requested)
        self._tree.new_session_with_cwd.connect(self.new_session_with_cwd)
        self._tree.selected_session_changed.connect(self._on_selection_changed)
        self._tree.cwd_exists_changed.connect(self._on_cwd_exists_changed)
        layout.addWidget(self._tree, 1)

        # ── Current Session ─────────────────────────────────────
        cur_group = QtWidgets.QGroupBox("Current Session")
        cur_group.setStyleSheet(self._GROUP_STYLE)
        cur_row = QtWidgets.QHBoxLayout(cur_group)
        cur_row.setSpacing(6)

        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.clicked.connect(self.reload_requested)
        cur_row.addWidget(reload_btn)

        new_btn = QtWidgets.QPushButton("New")
        new_btn.clicked.connect(self.new_requested)
        cur_row.addWidget(new_btn)

        import_btn = QtWidgets.QPushButton("Import")
        import_btn.clicked.connect(self.import_requested)
        cur_row.addWidget(import_btn)

        info_btn = QtWidgets.QPushButton("Session Info")
        info_btn.clicked.connect(self.session_info_requested)
        cur_row.addWidget(info_btn)

        cur_row.addStretch()
        layout.addWidget(cur_group)

        # ── Selected Session ────────────────────────────────────
        sel_group = QtWidgets.QGroupBox("Selected Session")
        sel_group.setStyleSheet(self._GROUP_STYLE)
        sel_layout = QtWidgets.QVBoxLayout(sel_group)
        sel_layout.setSpacing(4)

        # Row 1: main action buttons
        sel_row = QtWidgets.QHBoxLayout()
        sel_row.setSpacing(6)

        self._switch_btn = QtWidgets.QPushButton("Switch To")
        self._switch_btn.setEnabled(False)
        self._switch_btn.clicked.connect(
            lambda: self._tree.execute_action("switch"))
        sel_row.addWidget(self._switch_btn)

        self._new_session_btn = QtWidgets.QPushButton("New Session")
        self._new_session_btn.setEnabled(False)
        self._new_session_btn.clicked.connect(
            lambda: self._tree.execute_action("new_session"))
        sel_row.addWidget(self._new_session_btn)

        self._inspect_btn = QtWidgets.QPushButton("Inspect")
        self._inspect_btn.setEnabled(False)
        self._inspect_btn.clicked.connect(
            lambda: self._tree.execute_action("inspect"))
        sel_row.addWidget(self._inspect_btn)

        self._rename_btn = QtWidgets.QPushButton("Rename")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(
            lambda: self._tree.execute_action("rename"))
        sel_row.addWidget(self._rename_btn)

        self._delete_btn = QtWidgets.QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(
            lambda: self._tree.execute_action("delete"))
        sel_row.addWidget(self._delete_btn)

        sel_row.addStretch()
        sel_layout.addLayout(sel_row)

        # Row 2: Create working directory (hidden when CWD exists)
        self._create_dir_btn = QtWidgets.QPushButton("Create working directory")
        self._create_dir_btn.setVisible(False)
        self._create_dir_btn.clicked.connect(
            lambda: self._tree.execute_action("create_dir"))
        sel_layout.addWidget(self._create_dir_btn)

        layout.addWidget(sel_group)

        # ── Close button ────────────────────────────────────────
        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ── public helpers ──────────────────────────────────────────

    def refresh_sessions(
        self, session_dir: str | None, current_path: str | None
    ) -> None:
        """Tell the embedded tree to reload from *session_dir*."""
        self._current_session_path = current_path
        self._tree.set_sessions(session_dir, current_path)

    def set_current_session(self, path: str | None) -> None:
        """Highlight *path* in the embedded tree."""
        self._current_session_path = path
        self._tree.set_current_session(path)

    # ── button state ────────────────────────────────────────────

    def _on_cwd_exists_changed(self, exists: bool) -> None:
        """Show/hide the Create directory button when selection changes."""
        kind = self._tree.selected_item_kind
        self._create_dir_btn.setVisible(
            not exists and kind is not None
        )

    def _on_selection_changed(self, session_path: str | None) -> None:
        """Update selected-session buttons based on tree selection."""
        self._selected_session_path = session_path

        kind = self._tree.selected_item_kind
        cwd_exists = self._tree.selected_cwd_exists
        is_current = self._tree.selected_is_current

        is_session = kind in ("session", "fork") and bool(session_path)
        not_current = is_session and not is_current

        # Switch To — session/fork selected, not current, CWD exists
        self._switch_btn.setEnabled(not_current and cwd_exists)

        # New Session — any item with existing CWD
        self._new_session_btn.setEnabled(kind is not None and cwd_exists)

        # Inspect / Rename — session/fork only
        self._inspect_btn.setEnabled(is_session)
        self._rename_btn.setEnabled(is_session)

        # Delete — any item, not current
        self._delete_btn.setEnabled(kind is not None and not is_current)

        # Create directory — shown/hidden by _on_cwd_exists_changed
