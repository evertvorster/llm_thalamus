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

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import spaces_manager
from ui.spaces_widgets import (
    BrainPlaceholderWidget,
    CreateSpaceDialog,
    ObjectTypeDialog,
    ManageVersionsDialog,
)


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
        """
        Switch to the root 'Spaces' view and clear the current-space marker
        used by Thalamus for document exposure.
        """
        self._current_space_id = None
        try:
            # No space entered => no documents should be exposed.
            self._manager.set_current_space_id(None)
        except Exception:
            # Non-fatal; UI can still function even if this fails.
            pass

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

        delete_action = menu.addAction("Delete Space...")

        action = menu.exec(self.spaces_list.mapToGlobal(pos))
        if action == toggle_action:
            self._toggle_space_active(space_id)
        elif action == delete_action:
            self._delete_space(space)

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

    def _delete_space(self, space: spaces_manager.Space) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Space",
            f"Are you sure you want to delete the space:\n\n"
            f"    {space.name}\n\n"
            "Spaces can only be deleted if they contain no objects.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        try:
            self._manager.delete_space(space.id)
        except ValueError as e:
            # Space not empty → show explanatory error
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot Delete Space",
                str(e),
            )
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to delete space",
                f"Unexpected error:\n\n{e}",
            )
            return

        # Successful deletion → refresh UI
        self._update_header_for_root()
        self._refresh_spaces_list()

    # ------------------------------------------------------------------ Space view / Objects

    def _enter_space(self, space: spaces_manager.Space) -> None:
        """
        Enter a space in the UI and mark it as the current space whose
        documents will be exposed to Thalamus.
        """
        try:
            self._manager.set_current_space_id(space.id)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to enter space",
                f"Could not set this space as current:\n\n{e}",
            )
            return

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

        # After managing versions, the object may have been deleted
        # (if its last version was removed). Refresh the objects list.
        self._refresh_objects_list()
