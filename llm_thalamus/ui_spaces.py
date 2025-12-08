#!/usr/bin/env python3
"""
ui_spaces – Spaces & Objects UI panel for llm-thalamus.

This module provides the right-hand side panel that lives next to the chat UI.
It contains:

- A rectangular placeholder for the future "pulsating brain" eye-candy feature.
- A "Spaces" panel with:
    - Header label.
    - "Create Space" button.
    - A list of spaces (in-memory for now).

The storage / DB / OpenMemory integration will be handled by a separate
manager module later. This file focuses purely on the UI layer.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets


class BrainPlaceholderWidget(QtWidgets.QFrame):
    """
    Rectangular placeholder for the future pulsating brain feature.

    - Fixed height.
    - Light border.
    - Centered label text.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        # Give it a sensible fixed height; width will follow layout
        self.setMinimumHeight(100)
        self.setMaximumHeight(160)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        label = QtWidgets.QLabel("Brain Placeholder")
        label.setAlignment(QtCore.Qt.AlignCenter)

        font = label.font()
        font.setPointSize(font.pointSize() + 1)
        font.setBold(True)
        label.setFont(font)

        # Light background to make it visually stand out a bit
        self.setStyleSheet(
            """
            QFrame {
                background-color: #f5f5f5;
                border: 1px dashed #999999;
                border-radius: 6px;
            }
            """
        )

        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)


class CreateSpaceDialog(QtWidgets.QDialog):
    """
    Dialog for creating a new Space.

    Fields:
      - Name the new Space (line edit)
      - Short description of this space (multi-line text)

    Buttons:
      - Help (information)
      - Cancel
      - Create
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Create New Space")
        self.setModal(True)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        form_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(6)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Thalamus Design, Dynamic Power, Personal Journal")

        self.description_edit = QtWidgets.QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            "Short description of this space...\n\n"
            "Example: Notes and documents related to the llm-thalamus engine, "
            "UI, and memory design."
        )
        self.description_edit.setMinimumHeight(80)

        form_layout.addRow("Name the new Space", self.name_edit)
        form_layout.addRow("Short description of this space", self.description_edit)

        main_layout.addLayout(form_layout)

        # Buttons row: Help, spacer, Cancel / Create
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setContentsMargins(0, 8, 0, 0)

        self.help_button = QtWidgets.QPushButton("?")
        self.help_button.setToolTip(
            "A Space is a high-level bucket for documents.\n\n"
            "Use Spaces to group files by project, topic, or world. "
            "Files ingested inside a Space will later be used as context "
            "for the LLM (when the Space and its Objects are active)."
        )
        self.help_button.clicked.connect(self._on_help_clicked)

        button_layout.addWidget(self.help_button, 0, QtCore.Qt.AlignLeft)
        button_layout.addStretch(1)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)

        self.create_button = QtWidgets.QPushButton("Create")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create_clicked)

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.create_button)

        main_layout.addLayout(button_layout)

    def _on_help_clicked(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "About Spaces",
            "Spaces are conceptual containers for your documents.\n\n"
            "- Use one Space per project or area of interest.\n"
            "- Files ingested into a Space will later become structured context\n"
            "  for the LLM, controlled via active/inactive flags.\n\n"
            "This dialog just sets up the name and description. "
            "You'll add documents (Objects) to the Space afterwards.",
        )

    def _on_create_clicked(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing name",
                "Please provide a name for the new Space.",
            )
            return

        # No other validation yet; description can be empty.
        self.accept()

    def get_values(self) -> tuple[str, str]:
        """Return (name, description) after accept()."""
        return (
            self.name_edit.text().strip(),
            self.description_edit.toPlainText().strip(),
        )


class SpacesPanel(QtWidgets.QWidget):
    """
    Right-hand panel that hosts:

    - BrainPlaceholderWidget
    - Spaces header + "Create Space" button
    - A list of spaces (for now in-memory only)

    This is the visual home for the Spaces & Objects feature.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self._spaces: List[dict] = []  # in-memory placeholder

        self._build_ui()

    # ------------------------------------------------------------------ UI construction

    def _build_ui(self) -> None:
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 0, 0, 0)
        outer_layout.setSpacing(6)

        # Brain placeholder on top
        self.brain_placeholder = BrainPlaceholderWidget(self)
        outer_layout.addWidget(self.brain_placeholder, 0)

        # Below: Spaces panel
        spaces_container = QtWidgets.QFrame(self)
        spaces_container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        spaces_container.setFrameShadow(QtWidgets.QFrame.Raised)

        spaces_layout = QtWidgets.QVBoxLayout(spaces_container)
        spaces_layout.setContentsMargins(8, 8, 8, 8)
        spaces_layout.setSpacing(6)

        # Header row: "Spaces" label + "Create Space" button
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        spaces_label = QtWidgets.QLabel("Spaces")
        header_font = spaces_label.font()
        header_font.setBold(True)
        spaces_label.setFont(header_font)

        self.create_space_button = QtWidgets.QPushButton("Create Space")
        self.create_space_button.clicked.connect(self._on_create_space_clicked)

        header_layout.addWidget(spaces_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.create_space_button)

        spaces_layout.addLayout(header_layout)

        # List of spaces
        self.spaces_list = QtWidgets.QListWidget()
        self.spaces_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.spaces_list.setAlternatingRowColors(True)
        self.spaces_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.spaces_list.customContextMenuRequested.connect(
            self._on_spaces_context_menu
        )

        spaces_layout.addWidget(self.spaces_list, 1)

        outer_layout.addWidget(spaces_container, 1)

        # Give the whole panel a reasonable fixed width so it doesn't dominate
        self.setMinimumWidth(260)
        self.setMaximumWidth(420)

    # ------------------------------------------------------------------ Space handling (UI-only for now)

    def _on_create_space_clicked(self) -> None:
        dlg = CreateSpaceDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            name, description = dlg.get_values()
            self._add_space(name=name, description=description, active=True)

    def _add_space(self, name: str, description: str, active: bool = True) -> None:
        """
        Add a new space entry to the list (UI-only placeholder).

        Later this will call a real spaces_manager to create a row in SQLite and
        then update the UI from the DB.
        """
        space_id = len(self._spaces) + 1  # temporary in-memory id

        space = {
            "id": space_id,
            "name": name,
            "description": description,
            "active": bool(active),
        }
        self._spaces.append(space)

        item = QtWidgets.QListWidgetItem(name)
        item.setData(QtCore.Qt.UserRole, space_id)

        if not active:
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))

        self.spaces_list.addItem(item)

    def _on_spaces_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.spaces_list.itemAt(pos)
        if not item:
            return

        space_id = item.data(QtCore.Qt.UserRole)
        space = self._get_space_by_id(space_id)
        if not space:
            return

        menu = QtWidgets.QMenu(self)

        # Simple active/inactive toggle for now
        if space["active"]:
            toggle_action = menu.addAction("Deactivate Space")
        else:
            toggle_action = menu.addAction("Activate Space")

        action = menu.exec(self.spaces_list.mapToGlobal(pos))
        if action == toggle_action:
            self._toggle_space_active(space_id)

    def _get_space_by_id(self, space_id: int) -> Optional[dict]:
        for s in self._spaces:
            if s["id"] == space_id:
                return s
        return None

    def _toggle_space_active(self, space_id: int) -> None:
        space = self._get_space_by_id(space_id)
        if not space:
            return

        space["active"] = not space["active"]

        # Update item appearance
        for i in range(self.spaces_list.count()):
            item = self.spaces_list.item(i)
            if item.data(QtCore.Qt.UserRole) == space_id:
                if space["active"]:
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsEnabled)
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#000000")))
                else:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))
                break
