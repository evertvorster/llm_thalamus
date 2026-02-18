import json
from PySide6 import QtCore, QtWidgets


def _parse_ollama_list_models(stdout: str) -> set[str]:
    models: set[str] = set()
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("name"):
            continue
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


class OllamaModelPickerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, *, title: str, models: list[str], preselect: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 420)

        layout = QtWidgets.QVBoxLayout(self)

        self.status_label = QtWidgets.QLabel("Select a model:")
        layout.addWidget(self.status_label)

        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filter…")
        layout.addWidget(self.filter_edit)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.ok_button = QtWidgets.QPushButton("OK")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        btn_row.addWidget(self.ok_button)
        btn_row.addWidget(self.cancel_button)
        layout.addLayout(btn_row)

        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())

        self._all_models = models[:]
        self._preselect = (preselect or "").strip()

        self._apply_filter()
        self._apply_preselect()

    def _on_selection_changed(self):
        self.ok_button.setEnabled(bool(self.list_widget.selectedItems()))

    def _apply_filter(self):
        needle = self.filter_edit.text().strip().lower()
        self.list_widget.clear()
        if not needle:
            self.list_widget.addItems(self._all_models)
            return
        self.list_widget.addItems([m for m in self._all_models if needle in m.lower()])

    def _apply_preselect(self):
        if not self._preselect:
            return
        items = self.list_widget.findItems(self._preselect, QtCore.Qt.MatchExactly)
        if items:
            self.list_widget.setCurrentItem(items[0])

    def selected_model(self) -> str | None:
        items = self.list_widget.selectedItems()
        if not items:
            return None
        return items[0].text()


class ConfigDialog(QtWidgets.QDialog):
    configApplied = QtCore.Signal(dict, bool)

    _META_SECTION_KEYS = {"ui_descriptions"}

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thalamus Configuration")
        self.setModal(True)

        # Deep copies:
        # - _orig_config never changes (used to restore required fields)
        # - _config is the working copy
        self._orig_config = json.loads(json.dumps(config))
        self._config = json.loads(json.dumps(config))

        self._fields: dict[tuple, QtWidgets.QWidget] = {}

        self._ollama_models: set[str] | None = None
        self._ollama_list_error: str | None = None

        self._banner_label: QtWidgets.QLabel | None = None

        self._build_ui()
        self._load_values()
        self._start_ollama_list()

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

    # ---------- labels ----------

    def _label_for_path(self, path: tuple) -> str:
        full_key = ".".join(str(p) for p in path)
        ui_desc = self._config.get("ui_descriptions", {})
        if isinstance(ui_desc, dict):
            label = ui_desc.get(full_key)
            if isinstance(label, str) and label.strip():
                return label

        label_path = path[1:] if len(path) > 1 else path
        return ".".join(str(p) for p in label_path) or str(path[-1])

    # ---------- special-case detection ----------

    @staticmethod
    def _is_langgraph_node_model_path(path: tuple) -> bool:
        # ("llm", "roles", "<role>", "model")
        return (
            len(path) == 4
            and path[0] == "llm"
            and path[1] == "roles"
            and isinstance(path[2], str)
            and path[3] == "model"
        )
        return (
            len(path) == 3
            and path[0] == "llm"
            and path[1] == "langgraph_nodes"
            and isinstance(path[2], str)
        )

    # ---------- UI building ----------

    def _create_langgraph_model_field(self, path: tuple, value, grid_layout, row_ref):
        label_text = self._label_for_path(path)
        row = row_ref[0]

        label = QtWidgets.QLabel(label_text)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        value_label = QtWidgets.QLabel("" if value is None else str(value))
        value_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        change_btn = QtWidgets.QPushButton("Change…")
        change_btn.clicked.connect(lambda: self._on_change_langgraph_node_model_clicked(path))

        h = QtWidgets.QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(value_label, 1)
        h.addWidget(change_btn, 0)

        rhs = QtWidgets.QWidget()
        rhs.setLayout(h)

        grid_layout.addWidget(label, row, 0)
        grid_layout.addWidget(rhs, row, 1)

        self._fields[path] = value_label
        row_ref[0] += 1

    def _create_field(self, path: tuple, value, grid_layout, row_ref):
        if self._is_langgraph_node_model_path(path):
            self._create_langgraph_model_field(path, value, grid_layout, row_ref)
            return

        label_text = self._label_for_path(path)
        row = row_ref[0]

        if isinstance(value, bool):
            checkbox = QtWidgets.QCheckBox(label_text)
            grid_layout.addWidget(checkbox, row, 0, 1, 2)
            self._fields[path] = checkbox
        else:
            edit = QtWidgets.QLineEdit()
            edit.setMinimumWidth(250)

            label = QtWidgets.QLabel(label_text)
            label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

            grid_layout.addWidget(edit, row, 0)
            grid_layout.addWidget(label, row, 1)

            grid_layout.setColumnStretch(0, 1)
            grid_layout.setColumnStretch(1, 0)

            self._fields[path] = edit

        row_ref[0] += 1

    def _add_section_fields(self, value, path: tuple, grid_layout, row_ref):
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                sub_value = value[key]
                sub_path = path + (key,)
                if isinstance(sub_value, dict):
                    self._add_section_fields(sub_value, sub_path, grid_layout, row_ref)
                else:
                    self._create_field(sub_path, sub_value, grid_layout, row_ref)
        else:
            self._create_field(path, value, grid_layout, row_ref)

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self._banner_label = QtWidgets.QLabel("")
        self._banner_label.setWordWrap(True)
        self._banner_label.hide()
        main_layout.addWidget(self._banner_label, 0)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        for section_key in sorted(self._config.keys()):
            if section_key in self._META_SECTION_KEYS:
                continue

            section_value = self._config[section_key]

            group = QtWidgets.QGroupBox(str(section_key))
            grid = QtWidgets.QGridLayout()
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)

            row_ref = [0]
            self._add_section_fields(section_value, (section_key,), grid, row_ref)

            group.setLayout(grid)
            container_layout.addWidget(group)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self.save_button = QtWidgets.QPushButton("Save")
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.cancel_button = QtWidgets.QPushButton("Cancel")

        self.save_button.clicked.connect(self._on_save_clicked)
        self.apply_button.clicked.connect(self._on_apply_clicked)
        self.cancel_button.clicked.connect(self.reject)

        btn_row.addWidget(self.save_button)
        btn_row.addWidget(self.apply_button)
        btn_row.addWidget(self.cancel_button)

        main_layout.addLayout(btn_row)

    # ---------- ollama availability scan ----------

    def _start_ollama_list(self) -> None:
        self._ollama_models = None
        self._ollama_list_error = None

        self._ollama_proc = QtCore.QProcess(self)
        self._ollama_proc.finished.connect(self._on_ollama_list_finished)
        self._ollama_proc.start("ollama", ["list"])

    def _on_ollama_list_finished(self) -> None:
        stdout = self._ollama_proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        stderr = self._ollama_proc.readAllStandardError().data().decode("utf-8", errors="ignore")

        if self._ollama_proc.exitCode() != 0:
            self._ollama_list_error = (stderr.strip() or "Failed to run 'ollama list'.")
            self._ollama_models = None
            self._show_banner(
                "Warning: could not query Ollama models via `ollama list`.\n\n"
                f"{self._ollama_list_error}"
            )
            self._refresh_langgraph_model_styles()
            return

        self._hide_banner()
        self._ollama_models = _parse_ollama_list_models(stdout)
        self._refresh_langgraph_model_styles()

    def _show_banner(self, text: str) -> None:
        if not self._banner_label:
            return
        self._banner_label.setText(text)
        self._banner_label.setStyleSheet("font-weight: bold; color: #b00020;")
        self._banner_label.show()

    def _hide_banner(self) -> None:
        if not self._banner_label:
            return
        self._banner_label.hide()
        self._banner_label.setText("")
        self._banner_label.setStyleSheet("")

    def _refresh_langgraph_model_styles(self) -> None:
        models = self._ollama_models  # None => unknown

        for path, widget in self._fields.items():
            if not self._is_langgraph_node_model_path(path):
                continue
            if not isinstance(widget, QtWidgets.QLabel):
                continue

            configured = self._get_value_at_path(self._config, path)
            configured_str = "" if configured is None else str(configured).strip()

            if not configured_str or models is None:
                widget.setStyleSheet("")
                widget.setToolTip("")
                continue

            if configured_str not in models:
                widget.setStyleSheet("font-weight: bold; color: #b00020;")
                widget.setToolTip("Configured model not found in `ollama list`")
            else:
                widget.setStyleSheet("")
                widget.setToolTip("")

    # ---------- model picking ----------

    def _on_change_langgraph_node_model_clicked(self, path: tuple) -> None:
        node_name = path[2]

        if not self._ollama_models:
            QtWidgets.QMessageBox.warning(
                self,
                "Models unavailable",
                "Model list is not available. Ensure Ollama is installed and running, "
                "and that `ollama list` works in a terminal.",
            )
            return

        current = self._get_value_at_path(self._config, path)
        current_str = "" if current is None else str(current).strip()

        models_sorted = sorted(self._ollama_models)
        dlg = OllamaModelPickerDialog(
            self,
            title=f"Select model for {node_name}",
            models=models_sorted,
            preselect=current_str,
        )
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        model = dlg.selected_model()
        if not model:
            return

        self._set_value_at_path(self._config, path, model)
        w = self._fields.get(path)
        if isinstance(w, QtWidgets.QLabel):
            w.setText(model)

        self._refresh_langgraph_model_styles()

    # ---------- value handling ----------

    def _load_values(self):
        for path, widget in self._fields.items():
            value = self._get_value_at_path(self._config, path)

            if isinstance(widget, QtWidgets.QLabel) and self._is_langgraph_node_model_path(path):
                widget.setText("" if value is None else str(value))
                continue

            if isinstance(widget, QtWidgets.QCheckBox):
                widget.setChecked(bool(value))
                continue

            if isinstance(value, str) or value is None:
                text = "" if value is None else value
            else:
                try:
                    text = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    text = str(value)

            widget.setText(text)

        self._refresh_langgraph_model_styles()

    def _parse_new_value(self, text: str, old_value):
        if isinstance(old_value, str):
            if text.strip() == "":
                return old_value
            return text

        raw = text.strip()
        if raw == "":
            return old_value

        try:
            return json.loads(raw)
        except Exception:
            pass

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
        """
        Build a fresh config dict from widgets.

        Additionally: enforce that required fields (like final) are never
        accidentally cleared by restoring from the original config snapshot.
        """
        new_cfg = json.loads(json.dumps(self._config))

        for path, widget in self._fields.items():
            old_value = self._get_value_at_path(new_cfg, path)

            if self._is_langgraph_node_model_path(path) and isinstance(widget, QtWidgets.QLabel):
                new_value = widget.text().strip()
                if new_value == "":
                    new_value = old_value
                self._set_value_at_path(new_cfg, path, new_value)
                continue

            if isinstance(widget, QtWidgets.QCheckBox):
                new_value = bool(widget.isChecked())
            else:
                new_value = self._parse_new_value(widget.text(), old_value)

            self._set_value_at_path(new_cfg, path, new_value)

        # ---- required-field restore (belt-and-braces) ----
        orig_final = self._get_value_at_path(self._orig_config, ("llm", "langgraph_nodes", "final"))
        cur_final = self._get_value_at_path(new_cfg, ("llm", "langgraph_nodes", "final"))

        if (not isinstance(cur_final, str)) or (not cur_final.strip()):
            # Restore if we have a sane original value
            if isinstance(orig_final, str) and orig_final.strip():
                self._set_value_at_path(new_cfg, ("llm", "langgraph_nodes", "final"), orig_final)

        self._config = new_cfg
        self._refresh_langgraph_model_styles()

    # ---------- validation ----------

    def _validate_required(self) -> bool:
        final_model = self._get_value_at_path(self._config, ("llm", "langgraph_nodes", "final"))
        if not isinstance(final_model, str) or not final_model.strip():
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid config",
                "llm.langgraph_nodes.final is required and cannot be empty.",
            )
            return False
        return True

    # ---------- button handlers ----------

    def _on_save_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
        self.accept()

    def _on_apply_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
