from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import spaces_manager


class BrainPlaceholderWidget(QtWidgets.QFrame):
    """
    Rectangular placeholder / container for the pulsating brain.
    The actual BrainWidget will be inserted here by the main window.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        self.setMinimumHeight(220)
        self.setMaximumHeight(330)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Pure black background – the BrainWidget will sit on top of this.
        self.setStyleSheet(
            """
            QFrame {
                background-color: #000000;
                border: 1px solid #222222;
                border-radius: 6px;
            }
            """
        )

        # Leave the layout empty; the main window will insert the BrainWidget.
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
        self.name_edit.setPlaceholderText(
            "e.g. Thalamus Design, Dynamic Power, Personal Journal"
        )

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

        label = QtWidgets.QLabel(
            "Select the type of object you want to create:", self
        )
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
        - Per-row delete control
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Active", "Ingested at", "Filename", ""]
        )
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
            ingested_item.setFlags(
                QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
            )
            self.table.setItem(row_idx, 1, ingested_item)

            # Filename
            filename_item = QtWidgets.QTableWidgetItem(v.filename)
            filename_item.setFlags(
                QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
            )
            self.table.setItem(row_idx, 2, filename_item)

            # Delete control (tiny button)
            delete_button = QtWidgets.QPushButton("✕")
            delete_button.setToolTip(
                "Delete this version (and its OpenMemory content)"
            )
            delete_button.setProperty("version_id", v.id)
            delete_button.clicked.connect(self._on_delete_version_clicked)
            self.table.setCellWidget(row_idx, 3, delete_button)

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

    def _on_delete_version_clicked(self) -> None:
        """
        Handle per-row delete button clicks.

        - Asks for confirmation.
        - Calls manager.delete_version(version_id).
        - Reloads the table.
        - If no versions remain (object deleted), closes the dialog.
        """
        sender = self.sender()
        if not isinstance(sender, QtWidgets.QPushButton):
            return

        version_id = sender.property("version_id")
        if version_id is None:
            return

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Version",
            "Are you sure you want to permanently delete this version?\n\n"
            "This will also delete its OpenMemory content.\n"
            "If this is the last version, the object will also be removed.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        try:
            self._manager.delete_version(int(version_id))
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Failed to delete version",
                f"Could not delete version:\n\n{e}",
            )
            return

        self._load_versions()
        if not self._versions:
            # Object is gone (no versions left); close the dialog.
            self.accept()
