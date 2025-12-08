#!/usr/bin/env python3
"""
ui_spaces – Spaces & Objects UI panel for llm-thalamus.

Current responsibilities:
- Display a brain placeholder panel at the top (for future pulsating brain feature).
- Display a "Spaces" panel with:
    - Root mode:
        - Header: "Spaces"
        - Primary button: "Create Space"
        - List (icon grid) of spaces (from spaces_manager / SQLite)
        - Context menu to activate/deactivate a space.
    - Space mode (inside a space):
        - Header: "Space: <Name>"
        - Back button: "← Spaces"
        - Primary button: "Create Object"
        - List of objects in that space (from spaces_manager).
        - Context menu on objects: "Manage Versions..."

Activation (entering a space) uses itemActivated, respecting KDE/system
single vs double click behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import spaces_manager


class BrainPlaceholderWidget(QtWidgets.QFrame):
    """
    Rectangular placeholder for the future pulsating brain feature.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

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

        self.accept()

    def get_values(self) -> tuple[str, str]:
        return (
            self.name_edit.text().strip(),
            self.description_edit.toPlainText().strip(),
        )


class ObjectTypeDialog(QtWidgets.QDialog):
    """
    Dialog that lets the user choose which type of object to create.

    For now we only wire 'Text File', but we already reserve buttons
    for future 'Image' and 'Audio' types.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Object")
        self.setModal(True)

        self.chosen_type: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        label = QtWidgets.QLabel("Select the type of object you want to create:", self)
        layout.addWidget(label)

        # Text file (enabled)
        btn_text = QtWidgets.QPushButton("Text File", self)
        btn_text.clicked.connect(self._choose_text)
        layout.addWidget(btn_text)

        # Image (placeholder for the future)
        btn_image = QtWidgets.QPushButton("Image (future)", self)
        btn_image.setEnabled(False)
        layout.addWidget(btn_image)

        # Audio (placeholder for the future)
        btn_audio = QtWidgets.QPushButton("Audio (future)", self)
        btn_audio.setEnabled(False)
        layout.addWidget(btn_audio)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # --- internal helpers ---

    def _choose_text(self) -> None:
        self.chosen_type = "text_file"
        self.accept()


class ManageVersionsDialog(QtWidgets.QDialog):
    """
    Dialog to manage versions for a single object.

    Features:
    - Show all versions with:
        - Active checkbox
        - Ingested at
        - Filename
    - "New Version" button:
        - Opens a file dialog
        - Enforces basename match
        - Calls manager.add_version(...)
        - Reloads table
    """

    def __init__(
        self,
        manager: spaces_manager.SpacesManager,
        object_id: int,
        object_name: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._manager = manager
        self._object_id = object_id
        self._object_name = object_name
        self._versions: list[spaces_manager.Version] = []
        self._updating = False  # guard to avoid recursive itemChanged

        self.setWindowTitle(f"Versions – {object_name}")
        self.resize(600, 300)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Top row with "New Version"
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.new_version_button = QtWidgets.QPushButton("New Version")
        self.new_version_button.clicked.connect(self._on_new_version_clicked)

        top_layout.addWidget(self.new_version_button)
        top_layout.addStretch(1)

        main_layout.addLayout(top_layout)

        # Table of versions
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Active", "Ingested at", "Filename"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)

        main_layout.addWidget(self.table, 1)

        # Bottom row: Close button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch(1)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        main_layout.addLayout(button_layout)

        self._load_versions()

    def _load_versions(self) -> None:
        self._updating = True
        try:
            self._versions = self._manager.list_versions(self._object_id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to load versions",
                f"Could not load versions for object:\n\n{e}",
            )
            self._updating = False
            return

        self.table.setRowCount(0)

        for row_idx, v in enumerate(self._versions):
            self.table.insertRow(row_idx)

            # Active checkbox
            active_item = QtWidgets.QTableWidgetItem()
            active_item.setFlags(
                QtCore.Qt.ItemIsUserCheckable
                | QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
            )
            active_item.setCheckState(
                QtCore.Qt.Checked if v.status == "active" else QtCore.Qt.Unchecked
            )
            # Store version_id in this item
            active_item.setData(QtCore.Qt.UserRole, v.id)
            self.table.setItem(row_idx, 0, active_item)

            # Ingested at
            ingested_item = QtWidgets.QTableWidgetItem(v.ingested_at)
            ingested_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row_idx, 1, ingested_item)

            # Filename
            filename_item = QtWidgets.QTableWidgetItem(v.filename)
            filename_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row_idx, 2, filename_item)

        self.table.resizeColumnsToContents()
        self._updating = False

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        """
        Handle checkbox toggles for active/inactive.
        """
        if self._updating:
            return

        row = item.row()
        col = item.column()
        if col != 0:  # only active checkbox column
            return

        version_id = item.data(QtCore.Qt.UserRole)
        if version_id is None:
            return

        new_status = "active" if item.checkState() == QtCore.Qt.Checked else "inactive"

        try:
            self._manager.set_version_status(version_id, new_status)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to update version",
                f"Could not change version status:\n\n{e}",
            )
            # revert checkbox
            self._updating = True
            item.setCheckState(
                QtCore.Qt.Unchecked if new_status == "active" else QtCore.Qt.Checked
            )
            self._updating = False

    def _on_new_version_clicked(self) -> None:
        """
        Add a new version: file dialog, enforce basename, call add_version, reload.
        """
        # File dialog
        dlg = QtWidgets.QFileDialog(self, "Select New Version")
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        # Start with current directory, but filter filename as a hint
        dlg.setNameFilters(
            [
                f"{self._object_name} (*)",
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
        basename = Path(file_path).name

        if basename != self._object_name:
            QtWidgets.QMessageBox.warning(
                self,
                "Filename mismatch",
                f"This object tracks files named:\n\n"
                f"    {self._object_name}\n\n"
                f"You selected:\n\n"
                f"    {basename}\n\n"
                "If you renamed the file, create a new object instead.",
            )
            return

        try:
            self._manager.add_version(self._object_id, file_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to add version",
                f"Could not add new version:\n\n{e}",
            )
            return

        self._load_versions()


class SpacesPanel(QtWidgets.QWidget):
    """
    Right-hand panel that hosts:

    - BrainPlaceholderWidget
    - A header bar
    - Either:
        - Root spaces view
        - Inside-space objects view
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self._manager = spaces_manager.get_manager()
        self._spaces: list[spaces_manager.Space] = []
        self._objects: list[spaces_manager.Object] = []
        self._current_space_id: Optional[int] = None

        self._space_icon: Optional[QtGui.QIcon] = None
        self._object_icon: Optional[QtGui.QIcon] = None

        self._build_ui()
        self._refresh_spaces_list()
        self._update_header_for_root()

    # ------------------------------------------------------------------ UI construction

    def _build_ui(self) -> None:
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 0, 0, 0)
        outer_layout.setSpacing(6)

        self.brain_placeholder = BrainPlaceholderWidget(self)
        outer_layout.addWidget(self.brain_placeholder, 0)

        spaces_container = QtWidgets.QFrame(self)
        spaces_container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        spaces_container.setFrameShadow(QtWidgets.QFrame.Raised)

        spaces_layout = QtWidgets.QVBoxLayout(spaces_container)
        spaces_layout.setContentsMargins(8, 8, 8, 8)
        spaces_layout.setSpacing(6)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QtWidgets.QLabel("Spaces")
        header_font = self.header_label.font()
        header_font.setBold(True)
        self.header_label.setFont(header_font)

        self.back_button = QtWidgets.QPushButton("← Spaces")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self._on_back_to_spaces_clicked)

        self.primary_button = QtWidgets.QPushButton("Create Space")
        self.primary_button.clicked.connect(self._on_primary_button_clicked)

        header_layout.addWidget(self.header_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.primary_button)

        spaces_layout.addLayout(header_layout)

        # Root view: spaces list (icon grid)
        self.spaces_list = QtWidgets.QListWidget()
        self.spaces_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.spaces_list.setAlternatingRowColors(True)
        self.spaces_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.spaces_list.customContextMenuRequested.connect(
            self._on_spaces_context_menu
        )
        self.spaces_list.itemActivated.connect(self._on_space_activated)

        # Icon-mode configuration
        self.spaces_list.setViewMode(QtWidgets.QListView.IconMode)
        self.spaces_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.spaces_list.setWrapping(True)
        self.spaces_list.setIconSize(QtCore.QSize(40, 40))
        self.spaces_list.setSpacing(8)

        # Space view: objects list
        self.objects_list = QtWidgets.QListWidget()
        self.objects_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.objects_list.setAlternatingRowColors(True)
        self.objects_list.setVisible(False)
        self.objects_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.objects_list.customContextMenuRequested.connect(
            self._on_objects_context_menu
        )

        # Icon-mode configuration for objects
        self.objects_list.setViewMode(QtWidgets.QListView.IconMode)
        self.objects_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.objects_list.setWrapping(True)
        self.objects_list.setIconSize(QtCore.QSize(40, 40))
        self.objects_list.setSpacing(8)

        spaces_layout.addWidget(self.spaces_list, 1)
        spaces_layout.addWidget(self.objects_list, 1)

        outer_layout.addWidget(spaces_container, 1)

        self.setMinimumWidth(260)
        self.setMaximumWidth(420)

        # Default icon for spaces
        icon = QtGui.QIcon.fromTheme("folder")
        if icon.isNull():
            icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        self._space_icon = icon

        # Default icon for objects (text-like files, for now)
        obj_icon = QtGui.QIcon.fromTheme("text-x-generic")
        if obj_icon.isNull():
            obj_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        self._object_icon = obj_icon

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

    # ------------------------------------------------------------------ Spaces handling

    def _refresh_spaces_list(self) -> None:
        self._spaces = self._manager.list_spaces(active_only=False)

        self.spaces_list.clear()
        for space in self._spaces:
            item = QtWidgets.QListWidgetItem()
            item.setText(space.name)
            item.setData(QtCore.Qt.UserRole, space.id)

            # Icon & alignment
            if self._space_icon is not None:
                item.setIcon(self._space_icon)
            item.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom)

            if not space.active:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))

            if space.description:
                item.setToolTip(space.description)

            self.spaces_list.addItem(item)

    def _on_primary_button_clicked(self) -> None:
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

        self._refresh_spaces_list()

    # ------------------------------------------------------------------ Space view / Objects

    def _enter_space(self, space: spaces_manager.Space) -> None:
        self._current_space_id = space.id
        self._update_header_for_space(space)
        self._refresh_objects_list()

    def _on_back_to_spaces_clicked(self) -> None:
        self._update_header_for_root()
        self._refresh_spaces_list()

    def _refresh_objects_list(self) -> None:
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
            item = QtWidgets.QListWidgetItem()
            item.setText(obj.name)
            item.setData(QtCore.Qt.UserRole, obj.id)

            # Icon & alignment
            if self._object_icon is not None:
                item.setIcon(self._object_icon)
            item.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom)

            if not obj.active:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
                item.setForeground(QtGui.QBrush(QtGui.QColor("#999999")))

            item.setToolTip(
                f"Type: {obj.object_type}\nCreated: {obj.created_at}"
            )

            self.objects_list.addItem(item)

    def _on_create_object_clicked(self) -> None:
        """
        Entry point for the 'Create Object' button.

        First ask which type of object to create (text/image/audio). For now,
        only 'text_file' is implemented.
        """
        if self._current_space_id is None:
            return

        dlg = ObjectTypeDialog(self)
        if dlg.exec() != QtWidgets.QDialog.Accepted or not dlg.chosen_type:
            return  # user cancelled

        obj_type = dlg.chosen_type

        if obj_type == "text_file":
            self._create_text_file_object()
        else:
            # Future: image/audio handlers will go here
            return

    def _create_text_file_object(self) -> None:
        """
        Create a text-file object in the current space:

        - Show file picker
        - Create object with type='text_file'
        - Ingest into OpenMemory via spaces_manager
        """
        if self._current_space_id is None:
            return

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

    # ------------------------------------------------------------------ Object context menu / Manage Versions

    def _on_objects_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.objects_list.itemAt(pos)
        if not item:
            return

        object_id = item.data(QtCore.Qt.UserRole)
        obj = self._get_object_by_id(object_id)
        if not obj:
            return

        menu = QtWidgets.QMenu(self)
        manage_versions_action = menu.addAction("Manage Versions...")

        action = menu.exec(self.objects_list.mapToGlobal(pos))
        if action == manage_versions_action:
            self._open_manage_versions_dialog(obj)

    def _get_object_by_id(self, object_id: int) -> Optional[spaces_manager.Object]:
        for o in self._objects:
            if o.id == object_id:
                return o
        return None

    def _open_manage_versions_dialog(self, obj: spaces_manager.Object) -> None:
        dlg = ManageVersionsDialog(
            manager=self._manager,
            object_id=obj.id,
            object_name=obj.name,
            parent=self,
        )
        dlg.exec()
