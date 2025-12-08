#!/usr/bin/env python3
"""
ui_spaces – Spaces & Objects UI panel for llm-thalamus.

Current responsibilities:
- Display a brain placeholder panel at the top (for future pulsating brain feature).
- Display a "Spaces" panel with:
    - Header + primary button.
    - Root mode:
        - Header: "Spaces"
        - Primary button: "Create Space"
        - List of spaces (from spaces_manager / SQLite)
        - Context menu to activate/deactivate a space.
    - Space mode (inside a space):
        - Header: "Space: <Name>"
        - Back button: "← Spaces"
        - Primary button: "Create Object"
        - List of objects in that space (from spaces_manager).

Activation (entering a space) follows the Qt / KDE setting:
- We use itemActivated; KDE single-click users get single-click activation,
  double-click users get double-click activation automatically.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import spaces_manager


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

        # Description can be empty.
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
    - A header bar
    - Either:
        - Root spaces view
        - Inside-space objects view

    Root mode:
        Header: "Spaces"
        Primary button: "Create Space"
        List: spaces_list

    Space mode:
        Header: "Space: <Name>"
        Back button visible
        Primary button: "Create Object"
        List: objects_list
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        # Backing manager (singleton)
        self._manager = spaces_manager.get_manager()
        # In-memory caches from spaces_manager
        self._spaces: list[spaces_manager.Space] = []
        self._objects: list[spaces_manager.Object] = []

        # Current navigation state
        self._current_space_id: Optional[int] = None

        self._build_ui()
        self._refresh_spaces_list()
        self._update_header_for_root()

    # ------------------------------------------------------------------ UI construction

    def _build_ui(self) -> None:
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 0, 0, 0)
        outer_layout.setSpacing(6)

        # Brain placeholder on top
        self.brain_placeholder = BrainPlaceholderWidget(self)
        outer_layout.addWidget(self.brain_placeholder, 0)

        # Below: main container
        spaces_container = QtWidgets.QFrame(self)
        spaces_container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        spaces_container.setFrameShadow(QtWidgets.QFrame.Raised)

        spaces_layout = QtWidgets.QVBoxLayout(spaces_container)
        spaces_layout.setContentsMargins(8, 8, 8, 8)
        spaces_layout.setSpacing(6)

        # Header row
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QtWidgets.QLabel("Spaces")
        header_font = self.header_label.font()
        header_font.setBold(True)
        self.header_label.setFont(header_font)

        # Back button (only visible in space mode)
        self.back_button = QtWidgets.QPushButton("← Spaces")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self._on_back_to_spaces_clicked)

        # Primary action button: "Create Space" or "Create Object" depending on mode
        self.primary_button = QtWidgets.QPushButton("Create Space")
        self.primary_button.clicked.connect(self._on_primary_button_clicked)

        header_layout.addWidget(self.header_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.primary_button)

        spaces_layout.addLayout(header_layout)

        # Root view: list of spaces
        self.spaces_list = QtWidgets.QListWidget()
        self.spaces_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.spaces_list.setAlternatingRowColors(True)
        self.spaces_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.spaces_list.customContextMenuRequested.connect(
            self._on_spaces_context_menu
        )
        # Respect KDE/sytem single/double click behavior via itemActivated
        self.spaces_list.itemActivated.connect(self._on_space_activated)

        # Space view: list of objects
        self.objects_list = QtWidgets.QListWidget()
        self.objects_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.objects_list.setAlternatingRowColors(True)
        self.objects_list.setVisible(False)

        spaces_layout.addWidget(self.spaces_list, 1)
        spaces_layout.addWidget(self.objects_list, 1)

        outer_layout.addWidget(spaces_container, 1)

        # Give the whole panel a reasonable fixed width so it doesn't dominate
        self.setMinimumWidth(260)
        self.setMaximumWidth(420)

    # ------------------------------------------------------------------ Header state

    def _update_header_for_root(self) -> None:
        self._current_space_id = None
        self.header_label.setText("Spaces")
        self.back_button.setVisible(False)
        self.primary_button.setText("Create Space")

        self.spaces_list.setVisible(True)
        self.objects_list.setVisible(False)

    def _update_header_for_space(self, space: spaces_manager.Space) -> None:
        self.header_label.setText(f"Space: {space.name}")
        self.back_button.setVisible(True)
        self.primary_button.setText("Create Object")

        self.spaces_list.setVisible(False)
        self.objects_list.setVisible(True)

    # ------------------------------------------------------------------ Root: Spaces handling

    def _refresh_spaces_list(self) -> None:
        """
        Reload spaces from spaces_manager and repopulate the list widget.
        """
        self._spaces = self._manager.list_spaces(active_only=False)

        self.spaces_list.clear()
        for space in self._spaces:
            item = QtWidgets.QListWidgetItem(space.name)
            item.setData(QtCore.Qt.UserRole, space.id)

            if not space.active:
                # Inactive: gray + disabled look
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))

            # Tooltip shows description
            if space.description:
                item.setToolTip(space.description)

            self.spaces_list.addItem(item)

    def _on_primary_button_clicked(self) -> None:
        """
        Dispatch primary button based on mode:
        - Root: Create Space
        - Inside space: Create Object
        """
        if self._current_space_id is None:
            self._on_create_space_clicked()
        else:
            self._on_create_object_clicked()

    def _on_create_space_clicked(self) -> None:
        dlg = CreateSpaceDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            name, description = dlg.get_values()
            try:
                self._manager.create_space(name=name, description=description)
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Failed to create space",
                    f"Could not create space:\n\n{e}",
                )
                return
            self._refresh_spaces_list()

    def _on_space_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        """
        Enter the clicked/activated space.
        Activation respects system (KDE) single vs double click behavior.
        """
        space_id = item.data(QtCore.Qt.UserRole)
        space = self._get_space_by_id(space_id)
        if not space:
            return
        self._enter_space(space)

    def _on_spaces_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.spaces_list.itemAt(pos)
        if not item:
            return

        space_id = item.data(QtCore.Qt.UserRole)
        space = self._get_space_by_id(space_id)
        if not space:
            return

        menu = QtWidgets.QMenu(self)

        if space.active:
            toggle_action = menu.addAction("Deactivate Space")
        else:
            toggle_action = menu.addAction("Activate Space")

        action = menu.exec(self.spaces_list.mapToGlobal(pos))
        if action == toggle_action:
            self._toggle_space_active(space_id)

    def _get_space_by_id(self, space_id: int) -> Optional[spaces_manager.Space]:
        for s in self._spaces:
            if s.id == space_id:
                return s
        return None

    def _toggle_space_active(self, space_id: int) -> None:
        space = self._get_space_by_id(space_id)
        if not space:
            return

        new_active = not space.active
        try:
            self._manager.set_space_active(space_id, new_active)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to update space",
                f"Could not change space status:\n\n{e}",
            )
            return

        # Reload from DB to keep everything in sync and sorted
        self._refresh_spaces_list()

    # ------------------------------------------------------------------ Space view: Objects

    def _enter_space(self, space: spaces_manager.Space) -> None:
        """
        Switch panel into the given space and show its objects.
        """
        self._current_space_id = space.id
        self._update_header_for_space(space)
        self._refresh_objects_list()

    def _on_back_to_spaces_clicked(self) -> None:
        """
        Return to root spaces view.
        """
        self._update_header_for_root()
        self._refresh_spaces_list()

    def _refresh_objects_list(self) -> None:
        """
        Load objects for the current space and display them.
        """
        self.objects_list.clear()
        self._objects = []

        if self._current_space_id is None:
            return

        try:
            self._objects = self._manager.list_objects(
                space_id=self._current_space_id, active_only=False
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to load objects",
                f"Could not load objects for space:\n\n{e}",
            )
            return

        if not self._objects:
            empty_item = QtWidgets.QListWidgetItem("(No objects yet)")
            empty_item.setFlags(QtCore.Qt.NoItemFlags)
            empty_item.setForeground(QtGui.QBrush(QtGui.QColor("#777777")))
            self.objects_list.addItem(empty_item)
            return

        for obj in self._objects:
            item = QtWidgets.QListWidgetItem(obj.name)
            item.setData(QtCore.Qt.UserRole, obj.id)

            if not obj.active:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))

            # Tooltip could show type and created_at
            item.setToolTip(
                f"Type: {obj.object_type}\nCreated: {obj.created_at}"
            )

            self.objects_list.addItem(item)

    def _on_create_object_clicked(self) -> None:
        """
        Create a new Object in the current space by ingesting a file
        as its first version.
        """
        if self._current_space_id is None:
            return

        # For now, we only support text files. Filter is advisory.
        dlg = QtWidgets.QFileDialog(self, "Select Text File")
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        dlg.setNameFilters(
            [
                "Text files (*.txt *.md *.rst *.adoc *.org)",
                "All files (*)",
            ]
        )
        if not dlg.exec():
            return

        selected_files = dlg.selectedFiles()
        if not selected_files:
            return

        file_path = selected_files[0]

        try:
            self._manager.create_object_for_file(
                space_id=self._current_space_id,
                file_path=file_path,
                object_type="text_file",
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to create object",
                f"Could not create object for file:\n\n{e}",
            )
            return

        self._refresh_objects_list()
