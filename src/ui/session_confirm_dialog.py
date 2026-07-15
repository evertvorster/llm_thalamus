"""SessionConfirmDialog — preview and confirm a session change.

Shows the target working directory, model, and thinking level before
the session starts.  The user can change model and thinking level,
or cancel the operation entirely.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ui.model_dialog import ModelPickerDialog


_THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"]


class SessionConfirmDialog(QtWidgets.QDialog):
    """Confirm a new or switched session before sending RPCs.

    Displays read-only CWD and clickable labels for model and thinking
    level.  On accept, the caller reads :attr:`selected_model_id`,
    :attr:`selected_provider`, and :attr:`selected_thinking_level`.

    Args:
        cwd: Target working directory for the session.
        available_models: Full model list from ``get_available_models``.
        scoped_ids: Currently scoped model IDs for cycling.
        current_model_id: Pre-selected model ID (from session file
            for existing sessions, or the previous session's model
            for new sessions).
        current_provider: Pre-selected provider for *current_model_id*.
        current_thinking_level: Pre-selected thinking level.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        cwd: str,
        available_models: list[dict],
        scoped_ids: set[str],
        current_model_id: str = "",
        current_provider: str = "",
        current_thinking_level: str = "off",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Session")
        self.resize(460, 200)
        self.setMinimumWidth(380)

        self._available_models = available_models
        self._scoped_ids: set[str] = set(scoped_ids)
        self._selected_model_id: str = current_model_id
        self._selected_provider: str = current_provider
        self._selected_thinking_level: str = current_thinking_level

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        # ── CWD (read-only) ────────────────────────────────────
        cwd_row = QtWidgets.QHBoxLayout()
        cwd_label = QtWidgets.QLabel("Working directory:")
        cwd_label.setStyleSheet("font-weight: bold;")
        cwd_value = QtWidgets.QLabel(cwd)
        cwd_value.setWordWrap(True)
        cwd_row.addWidget(cwd_label)
        cwd_row.addWidget(cwd_value, 1)
        layout.addLayout(cwd_row)

        # ── Model (clickable label) ─────────────────────────────
        model_row = QtWidgets.QHBoxLayout()
        model_label = QtWidgets.QLabel("Model:")
        model_label.setStyleSheet("font-weight: bold;")
        self._model_value = QtWidgets.QLabel(
            self._format_model_label(current_provider, current_model_id)
            if current_model_id else "Click to select…"
        )
        self._model_value.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._model_value.setStyleSheet("color: #1a73e8; text-decoration: underline;")
        self._model_value.mousePressEvent = lambda e: self._on_pick_model()
        model_row.addWidget(model_label)
        model_row.addWidget(self._model_value, 1)
        layout.addLayout(model_row)

        # ── Thinking level (clickable label) ────────────────────
        think_row = QtWidgets.QHBoxLayout()
        think_label = QtWidgets.QLabel("Thinking level:")
        think_label.setStyleSheet("font-weight: bold;")
        self._think_value = QtWidgets.QLabel(current_thinking_level)
        self._think_value.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._think_value.setStyleSheet("color: #1a73e8; text-decoration: underline;")
        self._think_value.mousePressEvent = lambda e: self._on_pick_thinking_level()
        think_row.addWidget(think_label)
        think_row.addWidget(self._think_value, 1)
        layout.addLayout(think_row)

        layout.addStretch(1)

        # ── Buttons ────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.clicked.connect(self._on_accept)
        ok_btn.setDefault(True)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    # ── public accessors ───────────────────────────────────────────

    @property
    def selected_model_id(self) -> str:
        return self._selected_model_id

    @property
    def selected_provider(self) -> str:
        return self._selected_provider

    @property
    def selected_thinking_level(self) -> str:
        return self._selected_thinking_level

    @property
    def selected_scoped_ids(self) -> set[str]:
        return self._scoped_ids.copy()

    # ── model picker ──────────────────────────────────────────────

    def _on_pick_model(self) -> None:
        """Open ModelPickerDialog and update selection."""
        dlg = ModelPickerDialog(self._available_models, self._scoped_ids, self)
        # Pre-select current model if it's in the list.
        if self._selected_model_id:
            dlg.select_model(self._selected_model_id)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            if dlg.selected_model_id:
                self._selected_model_id = dlg.selected_model_id
                self._selected_provider = dlg.selected_provider
                self._scoped_ids = dlg.scoped_ids
                self._model_value.setText(
                    self._format_model_label(
                        self._selected_provider, self._selected_model_id
                    )
                )

    # ── thinking level ────────────────────────────────────────────

    def _on_pick_thinking_level(self) -> None:
        """Show QMenu with thinking levels."""
        menu = QtWidgets.QMenu(self)
        for level in _THINKING_LEVELS:
            action = menu.addAction(level)
            action.setCheckable(True)
            if level == self._selected_thinking_level:
                action.setChecked(True)
        chosen = menu.exec(
            self._think_value.mapToGlobal(
                self._think_value.rect().bottomLeft()
            )
        )
        if chosen is not None:
            self._selected_thinking_level = chosen.text()
            self._think_value.setText(self._selected_thinking_level)

    # ── helpers ───────────────────────────────────────────────────

    def _format_model_label(self, provider: str, model_id: str) -> str:
        parts = []
        if provider:
            parts.append(f"({provider})")
        # Use model name if available, fall back to ID.
        name = model_id
        for m in self._available_models:
            if m.get("id") == model_id:
                candidate = m.get("name") or m.get("id") or ""
                if candidate:
                    name = candidate
                break
        parts.append(name)
        return " ".join(parts)

    def _on_accept(self) -> None:
        if not self._selected_model_id:
            QtWidgets.QMessageBox.warning(
                self,
                "No Model Selected",
                "Please select a model before continuing.",
            )
            return
        self.accept()
