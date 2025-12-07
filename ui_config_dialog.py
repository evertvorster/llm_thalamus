import json
from PySide6 import QtCore, QtWidgets


class ConfigDialog(QtWidgets.QDialog):
    """
    Generic, dynamic config editor.

    - Renders whatever structure is present in the config dict.
    - Top-level keys become group boxes.
    - Nested dict leaves become editable QLineEdits.
    - Types are preserved where possible (bool/int/float/list/dict via JSON).
    """
    configApplied = QtCore.Signal(dict, bool)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thalamus Configuration")
        self.setModal(True)

        # Work on a deep copy so we don't mutate the caller's dict directly
        self._config = json.loads(json.dumps(config))
        # Maps path tuples (e.g. ("logging", "thalamus_enabled")) to QLineEdit
        self._fields: dict[tuple, QtWidgets.QLineEdit] = {}

        self._build_ui()
        self._load_values()

        # Make it reasonably sized by default
        self.resize(640, 400)
        self.setMinimumWidth(480)

    # ---------- path helpers ----------

    @staticmethod
    def _get_value_at_path(cfg: dict, path: tuple):
        cur = cfg
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    @staticmethod
    def _set_value_at_path(cfg: dict, path: tuple, value):
        cur = cfg
        for key in path[:-1]:
            if not isinstance(cur, dict):
                return
            cur = cur.setdefault(key, {})
        cur[path[-1]] = value

    # ---------- UI building ----------

    def _create_field(self, path: tuple, value, grid_layout: QtWidgets.QGridLayout, row_ref):
        """
        Create a single line-edit for a leaf value.

        Text box goes on the LEFT (stretchy), description on the RIGHT.
        """
        if len(path) > 1:
            label_path = path[1:]
        else:
            label_path = path
        label_text = ".".join(str(p) for p in label_path) or str(path[-1])

        edit = QtWidgets.QLineEdit()
        edit.setMinimumWidth(250)

        label = QtWidgets.QLabel(label_text)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        row = row_ref[0]
        grid_layout.addWidget(edit, row, 0)
        grid_layout.addWidget(label, row, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 0)

        self._fields[path] = edit
        row_ref[0] += 1

    def _add_section_fields(self, value, path: tuple,
                            grid_layout: QtWidgets.QGridLayout, row_ref):
        """
        Recursively add fields for all leaves under a given section,
        placing them into the provided grid layout.
        """
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                sub_value = value[key]
                sub_path = path + (key,)
                if isinstance(sub_value, dict):
                    self._add_section_fields(sub_value, sub_path,
                                             grid_layout, row_ref)
                else:
                    self._create_field(sub_path, sub_value,
                                       grid_layout, row_ref)
        else:
            self._create_field(path, value, grid_layout, row_ref)

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        # One group box per top-level section
        for section_key in sorted(self._config.keys()):
            section_value = self._config[section_key]

            group = QtWidgets.QGroupBox(str(section_key))
            grid = QtWidgets.QGridLayout()
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)

            row_ref = [0]
            self._add_section_fields(section_value, (section_key,),
                                     grid, row_ref)

            group.setLayout(grid)
            container_layout.addWidget(group)

        container_layout.addStretch(1)
        scroll.setWidget(container)

        main_layout.addWidget(scroll, 1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self.save_button = QtWidgets.QPushButton("Save")
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.close_button = QtWidgets.QPushButton("Close")

        self.save_button.clicked.connect(self._on_save_clicked)
        self.apply_button.clicked.connect(self._on_apply_clicked)
        self.close_button.clicked.connect(self.reject)

        btn_row.addWidget(self.save_button)
        btn_row.addWidget(self.apply_button)
        btn_row.addWidget(self.close_button)

        main_layout.addLayout(btn_row)

    # ---------- value handling ----------

    def _load_values(self):
        for path, edit in self._fields.items():
            value = self._get_value_at_path(self._config, path)
            if isinstance(value, str) or value is None:
                text = "" if value is None else value
            else:
                try:
                    text = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    text = str(value)
            edit.setText(text)

    def _parse_new_value(self, text: str, old_value):
        if isinstance(old_value, str):
            return text

        raw = text.strip()
        if raw == "":
            # Empty means "keep old" for non-string values
            return old_value

        # Try JSON first (handles bool/int/float/list/dict/null)
        try:
            return json.loads(raw)
        except Exception:
            pass

        # Fall back to casting to the original type where it makes sense
        try:
            if isinstance(old_value, bool):
                lowered = raw.lower()
                if lowered in ("true", "1", "yes", "on"):
                    return True
                if lowered in ("false", "0", "no", "off"):
                    return False
                return old_value
            if isinstance(old_value, int):
                return int(raw)
            if isinstance(old_value, float):
                return float(raw)
        except Exception:
            return old_value

        return old_value

    def _apply_changes_to_config(self):
        new_cfg = json.loads(json.dumps(self._config))
        for path, edit in self._fields.items():
            old_value = self._get_value_at_path(new_cfg, path)
            new_value = self._parse_new_value(edit.text(), old_value)
            self._set_value_at_path(new_cfg, path, new_value)
        self._config = new_cfg

    # ---------- button handlers ----------

    def _on_save_clicked(self):
        self._apply_changes_to_config()
        self.configApplied.emit(self._config, True)
        self.accept()

    def _on_apply_clicked(self):
        self._apply_changes_to_config()
        self.configApplied.emit(self._config, True)
