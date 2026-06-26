"""SessionDialog — non‑modal dialog embedding the session tree + actions."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.widgets import SessionListWidget


class SessionDialog(QtWidgets.QDialog):
    """Non‑modal session manager dialog.

    Embeds a :class:`SessionListWidget` and exposes buttons for
    New / Reload / Import / Session Info / Inspect.

    Signals match those of :class:`SessionListWidget` plus dialog‑level
    actions:
        * ``new_requested()``
        * ``reload_requested()``
        * ``import_requested()``
        * ``session_info_requested()``
        * ``switch_requested(str)``
        * ``rename_requested(str, str)``
        * ``delete_requested(list)``
        * ``inspect_requested(str)``
    """

    new_requested = QtCore.Signal()
    reload_requested = QtCore.Signal()
    import_requested = QtCore.Signal()
    session_info_requested = QtCore.Signal()

    # Forwarded from the embedded SessionListWidget.
    switch_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    delete_requested = QtCore.Signal(list)
    inspect_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Session Manager")
        self.resize(620, 500)
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
        self._tree.new_session_requested.connect(self.new_requested)
        self._tree.selected_session_changed.connect(self._on_selection_changed)
        layout.addWidget(self._tree, 1)

        # ── action buttons ─────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)

        new_btn = QtWidgets.QPushButton("New")
        new_btn.clicked.connect(self.new_requested)
        btn_row.addWidget(new_btn)

        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.clicked.connect(self.reload_requested)
        btn_row.addWidget(reload_btn)

        import_btn = QtWidgets.QPushButton("Import")
        import_btn.clicked.connect(self.import_requested)
        btn_row.addWidget(import_btn)

        info_btn = QtWidgets.QPushButton("Session Info")
        info_btn.clicked.connect(self.session_info_requested)
        btn_row.addWidget(info_btn)

        inspect_btn = QtWidgets.QPushButton("Inspect")
        inspect_btn.setEnabled(False)
        inspect_btn.clicked.connect(lambda: self._tree.execute_action("inspect"))
        btn_row.addWidget(inspect_btn)
        self._inspect_btn = inspect_btn

        delete_btn = QtWidgets.QPushButton("Delete")
        delete_btn.setEnabled(False)
        delete_btn.clicked.connect(lambda: self._tree.execute_action("delete"))
        btn_row.addWidget(delete_btn)
        self._delete_btn = delete_btn

        btn_row.addStretch()

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

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

    # ── inspect button helpers ──────────────────────────────────

    def _on_selection_changed(self, session_path: str | None) -> None:
        """Enable Inspect and Delete buttons only when a non-current session is selected."""
        self._selected_session_path = session_path
        enabled = bool(session_path) and session_path != self._current_session_path
        self._inspect_btn.setEnabled(enabled)
        self._delete_btn.setEnabled(enabled)


