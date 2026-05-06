import json
from PySide6 import QtCore, QtWidgets

from runtime.providers.configured import (
    ProviderOption,
    ProviderModelStatus,
    active_provider_key,
    list_models_for_provider,
    missing_required_roles,
    provider_options_from_config,
)


class ModelPickerDialog(QtWidgets.QDialog):
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
    llmBackendsApplied = QtCore.Signal(dict)
    mcpConfigApplied = QtCore.Signal(dict)

    _META_SECTION_KEYS = {"ui_descriptions", "config_version"}

    def __init__(
        self,
        config: dict,
        llm_backends_config: dict,
        mcp_config: dict,
        *,
        mcp_runtime_config: dict | None = None,
        focused_server_id: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Thalamus Configuration")
        self.setModal(True)

        # Deep copies:
        # - _orig_config never changes (used to restore required fields)
        # - _config is the working copy
        self._orig_config = json.loads(json.dumps(config))
        self._config = json.loads(json.dumps(config))
        self._orig_llm_backends_config = json.loads(json.dumps(llm_backends_config))
        self._llm_backends_config = json.loads(json.dumps(llm_backends_config))
        self._orig_mcp_config = json.loads(json.dumps(mcp_config))
        self._mcp_config = json.loads(json.dumps(mcp_config))
        self._mcp_runtime_config = json.loads(
            json.dumps(mcp_runtime_config if isinstance(mcp_runtime_config, dict) else mcp_config)
        )
        self._focused_server_id = focused_server_id if isinstance(focused_server_id, str) else None

        self._fields: dict[tuple, QtWidgets.QWidget] = {}
        self._backend_field_edits: dict[str, QtWidgets.QWidget] = {}
        self._mcp_field_edits: dict[str, QtWidgets.QWidget] = {}
        self._tool_approval_boxes: dict[tuple[str, str], QtWidgets.QComboBox] = {}

        self._provider_options: list[ProviderOption] = provider_options_from_config(self._llm_backends_config)
        self._provider_models: set[str] | None = None
        self._provider_model_status: ProviderModelStatus | None = None

        self._banner_label: QtWidgets.QLabel | None = None
        self._tabs: QtWidgets.QTabWidget | None = None
        self._general_scroll: QtWidgets.QScrollArea | None = None
        self._backend_list: QtWidgets.QListWidget | None = None
        self._backend_detail_layout: QtWidgets.QVBoxLayout | None = None
        self._mcp_server_list: QtWidgets.QListWidget | None = None
        self._mcp_detail_container: QtWidgets.QWidget | None = None
        self._mcp_detail_layout: QtWidgets.QVBoxLayout | None = None

        self._build_ui()
        self._load_values()
        self._reload_provider_models()

        if self._focused_server_id:
            self._show_focused_server(self._focused_server_id)

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
        """
        Label resolution order:
        1) flat ui_descriptions lookup using a dotted key (legacy style)
        2) nested ui_descriptions lookup following the same dict structure as config
        3) fallback: join of path elements (excluding section key if possible)
        """
        full_key = ".".join(str(p) for p in path)
        ui_desc = self._config.get("ui_descriptions", {})

        # 1) flat mapping support (older configs)
        label = None
        if isinstance(ui_desc, dict):
            v = ui_desc.get(full_key)
            if isinstance(v, str) and v.strip():
                label = v

        # 2) nested mapping support (current config.json uses nested objects)
        if label is None and isinstance(ui_desc, dict):
            cur = ui_desc
            for p in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(p)
            if isinstance(cur, str) and cur.strip():
                label = cur

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

    @staticmethod
    def _is_provider_path(path: tuple) -> bool:
        return path == ("llm", "provider")

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
        if self._is_provider_path(path):
            self._create_provider_field(path, value, grid_layout, row_ref)
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

    def _create_provider_field(self, path: tuple, value, grid_layout, row_ref):
        label_text = self._label_for_path(path)
        row = row_ref[0]

        label = QtWidgets.QLabel(label_text)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        combo = QtWidgets.QComboBox()
        combo.setMinimumWidth(250)
        for index, option in enumerate(self._provider_options):
            combo.addItem(option.display_name, option.key)
            combo.setItemData(index, option.tooltip, QtCore.Qt.ToolTipRole)
        combo.currentIndexChanged.connect(self._on_provider_changed)

        grid_layout.addWidget(combo, row, 0)
        grid_layout.addWidget(label, row, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 0)

        self._fields[path] = combo
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

        self._tabs = QtWidgets.QTabWidget(self)
        main_layout.addWidget(self._tabs, 1)

        self._build_general_tab()
        self._build_backends_tab()
        self._build_mcp_tab()

        if self._tabs is not None and self._focused_server_id:
            self._tabs.setCurrentIndex(1)

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

    def _build_general_tab(self) -> None:
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._general_scroll = scroll
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
        if self._tabs is not None:
            self._tabs.addTab(scroll, "General")

    def _build_backends_tab(self) -> None:
        tab = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)

        self._backend_list = QtWidgets.QListWidget(tab)
        self._backend_list.currentItemChanged.connect(self._on_backend_changed)
        left_col.addWidget(self._backend_list, 1)

        btn_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add")
        remove_btn = QtWidgets.QPushButton("Remove")
        add_btn.clicked.connect(self._on_add_backend_clicked)
        remove_btn.clicked.connect(self._on_remove_backend_clicked)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        left_col.addLayout(btn_row)

        detail_scroll = QtWidgets.QScrollArea(tab)
        detail_scroll.setWidgetResizable(True)
        detail_container = QtWidgets.QWidget(detail_scroll)
        self._backend_detail_layout = QtWidgets.QVBoxLayout(detail_container)
        self._backend_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._backend_detail_layout.setSpacing(8)
        self._backend_detail_layout.addStretch(1)
        detail_scroll.setWidget(detail_container)

        layout.addLayout(left_col, 0)
        layout.addWidget(detail_scroll, 1)
        if self._tabs is not None:
            self._tabs.addTab(tab, "Backends")

        self._refresh_backend_list()

    def _backend_cfg(self, backend_id: str) -> dict | None:
        backends = self._llm_backends_config.get("backends", {}) if isinstance(self._llm_backends_config, dict) else {}
        if not isinstance(backends, dict):
            return None
        backend_cfg = backends.get(backend_id)
        return backend_cfg if isinstance(backend_cfg, dict) else None

    def _refresh_backend_list(self) -> None:
        if self._backend_list is None:
            return
        self._backend_list.clear()
        backends = self._llm_backends_config.get("backends", {}) if isinstance(self._llm_backends_config, dict) else {}
        if isinstance(backends, dict):
            for backend_id in sorted(backends.keys()):
                item = QtWidgets.QListWidgetItem(str(backend_id))
                item.setData(QtCore.Qt.UserRole, backend_id)
                self._backend_list.addItem(item)
        if self._backend_list.count() > 0:
            self._backend_list.setCurrentRow(0)
        else:
            self._render_backend(None)

    def _clear_backend_detail(self) -> None:
        if self._backend_detail_layout is None:
            return
        while self._backend_detail_layout.count():
            item = self._backend_detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._backend_field_edits = {}

    def _render_backend(self, backend_id: str | None) -> None:
        self._clear_backend_detail()
        if self._backend_detail_layout is None:
            return
        if not backend_id:
            self._backend_detail_layout.addWidget(QtWidgets.QLabel("No backend selected."))
            self._backend_detail_layout.addStretch(1)
            return
        backend_cfg = self._backend_cfg(backend_id)
        if not isinstance(backend_cfg, dict):
            self._backend_detail_layout.addWidget(QtWidgets.QLabel("Backend not found."))
            self._backend_detail_layout.addStretch(1)
            return

        header = QtWidgets.QLabel(str(backend_cfg.get("label") or backend_id))
        font = header.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        header.setFont(font)
        self._backend_detail_layout.addWidget(header)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        key_edit = QtWidgets.QLineEdit()
        key_edit.setText(backend_id)
        self._backend_field_edits["key"] = key_edit
        form.addRow("Key", key_edit)

        label_edit = QtWidgets.QLineEdit()
        self._backend_field_edits["label"] = label_edit
        form.addRow("Label", label_edit)

        kind_box = QtWidgets.QComboBox()
        kind_box.addItem("Ollama", "ollama")
        kind_box.addItem("OpenAI-compatible", "openai_compatible")
        kind_box.currentIndexChanged.connect(self._refresh_backend_kind_hint)
        self._backend_field_edits["kind"] = kind_box
        form.addRow("Connection type", kind_box)

        url_edit = QtWidgets.QLineEdit()
        self._backend_field_edits["url"] = url_edit
        form.addRow("Base URL", url_edit)

        api_key_env_edit = QtWidgets.QLineEdit()
        self._backend_field_edits["api_key_env"] = api_key_env_edit
        form.addRow("API key env", api_key_env_edit)

        api_token_env_edit = QtWidgets.QLineEdit()
        self._backend_field_edits["api_token_env"] = api_token_env_edit
        form.addRow("API token env", api_token_env_edit)

        self._backend_detail_layout.addLayout(form)

        kind_hint = QtWidgets.QLabel("")
        kind_hint.setWordWrap(True)
        self._backend_field_edits["kind_hint"] = kind_hint
        self._backend_detail_layout.addWidget(kind_hint)

        status = list_models_for_provider(self._llm_backends_config, backend_id)
        lines = [
            f"Connection type: {status.kind or '-'}",
            f"URL: {status.url or '-'}",
        ]
        if status.error:
            lines.append(f"Model discovery error: {status.error}")
        else:
            lines.append(f"Models discovered: {len(status.models)}")
        status_label = QtWidgets.QLabel("\n".join(lines))
        status_label.setWordWrap(True)
        self._backend_detail_layout.addWidget(status_label)
        self._backend_detail_layout.addStretch(1)
        self._load_backend_values(backend_id)

    def _load_backend_values(self, backend_id: str) -> None:
        backend_cfg = self._backend_cfg(backend_id)
        if not isinstance(backend_cfg, dict):
            return
        if isinstance(self._backend_field_edits.get("label"), QtWidgets.QLineEdit):
            self._backend_field_edits["label"].setText(str(backend_cfg.get("label") or backend_id))
        kind_box = self._backend_field_edits.get("kind")
        if isinstance(kind_box, QtWidgets.QComboBox):
            idx = kind_box.findData(str(backend_cfg.get("kind") or "").strip())
            if idx >= 0:
                kind_box.setCurrentIndex(idx)
        if isinstance(self._backend_field_edits.get("url"), QtWidgets.QLineEdit):
            self._backend_field_edits["url"].setText(str(backend_cfg.get("url") or ""))
        if isinstance(self._backend_field_edits.get("api_key_env"), QtWidgets.QLineEdit):
            self._backend_field_edits["api_key_env"].setText(str(backend_cfg.get("api_key_env") or ""))
        if isinstance(self._backend_field_edits.get("api_token_env"), QtWidgets.QLineEdit):
            self._backend_field_edits["api_token_env"].setText(str(backend_cfg.get("api_token_env") or ""))
        self._refresh_backend_kind_hint()

    def _apply_backend_changes(self, backend_id: str) -> None:
        backend_cfg = self._backend_cfg(backend_id)
        if not isinstance(backend_cfg, dict):
            return
        label_edit = self._backend_field_edits.get("label")
        kind_box = self._backend_field_edits.get("kind")
        url_edit = self._backend_field_edits.get("url")
        api_key_env_edit = self._backend_field_edits.get("api_key_env")
        api_token_env_edit = self._backend_field_edits.get("api_token_env")
        key_edit = self._backend_field_edits.get("key")
        new_backend_id = backend_id
        if isinstance(key_edit, QtWidgets.QLineEdit):
            candidate = key_edit.text().strip()
            if candidate:
                new_backend_id = candidate
        if isinstance(label_edit, QtWidgets.QLineEdit):
            backend_cfg["label"] = label_edit.text().strip() or backend_id
        if isinstance(kind_box, QtWidgets.QComboBox):
            backend_cfg["kind"] = str(kind_box.currentData() or "").strip()
        if isinstance(url_edit, QtWidgets.QLineEdit):
            backend_cfg["url"] = url_edit.text().strip()
        if isinstance(api_key_env_edit, QtWidgets.QLineEdit):
            backend_cfg["api_key_env"] = api_key_env_edit.text().strip() or None
        if isinstance(api_token_env_edit, QtWidgets.QLineEdit):
            backend_cfg["api_token_env"] = api_token_env_edit.text().strip() or None
        if new_backend_id != backend_id:
            backends = self._llm_backends_config.get("backends", {})
            if isinstance(backends, dict):
                if new_backend_id in backends:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Duplicate backend key",
                        f"A backend with key '{new_backend_id}' already exists.",
                    )
                else:
                    backends[new_backend_id] = backends.pop(backend_id)
                    if self._active_provider_key() == backend_id:
                        self._set_value_at_path(self._config, ("llm", "provider"), new_backend_id)
                    if self._backend_list is not None and self._backend_list.currentItem() is not None:
                        self._backend_list.currentItem().setText(new_backend_id)
                        self._backend_list.currentItem().setData(QtCore.Qt.UserRole, new_backend_id)

    def _refresh_backend_kind_hint(self) -> None:
        kind_box = self._backend_field_edits.get("kind")
        hint_label = self._backend_field_edits.get("kind_hint")
        if not isinstance(kind_box, QtWidgets.QComboBox) or not isinstance(hint_label, QtWidgets.QLabel):
            return
        kind = str(kind_box.currentData() or "").strip()
        if kind == "ollama":
            hint_label.setText("Ollama uses the native API root. Typical URL: http://localhost:11434")
        else:
            hint_label.setText("OpenAI-compatible backends usually use a /v1 API root. Typical URL: http://host:port/v1")

    def _on_backend_changed(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None) -> None:
        if previous is not None:
            previous_id = str(previous.data(QtCore.Qt.UserRole) or "")
            if previous_id:
                self._apply_backend_changes(previous_id)
        current_id = str(current.data(QtCore.Qt.UserRole) or "") if current is not None else None
        self._render_backend(current_id)
        self._provider_options = provider_options_from_config(self._llm_backends_config)
        self._reload_provider_models()

    def _on_add_backend_clicked(self) -> None:
        backends = self._llm_backends_config.setdefault("backends", {})
        if not isinstance(backends, dict):
            backends = {}
            self._llm_backends_config["backends"] = backends
        base = "backend"
        i = 1
        backend_id = f"{base}_{i}"
        while backend_id in backends:
            i += 1
            backend_id = f"{base}_{i}"
        backends[backend_id] = {
            "label": f"Backend {i}",
            "kind": "openai_compatible",
            "url": "",
            "api_key_env": None,
            "api_token_env": None,
        }
        self._provider_options = provider_options_from_config(self._llm_backends_config)
        self._refresh_provider_combo()
        self._refresh_backend_list()
        if self._backend_list is not None:
            for idx in range(self._backend_list.count()):
                item = self._backend_list.item(idx)
                if str(item.data(QtCore.Qt.UserRole) or "") == backend_id:
                    self._backend_list.setCurrentRow(idx)
                    break

    def _on_remove_backend_clicked(self) -> None:
        if self._backend_list is None or self._backend_list.currentItem() is None:
            return
        backend_id = str(self._backend_list.currentItem().data(QtCore.Qt.UserRole) or "")
        if not backend_id:
            return
        if backend_id == self._active_provider_key():
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot remove active backend",
                "Select a different active backend before removing this one.",
            )
            return
        backends = self._llm_backends_config.get("backends", {})
        if isinstance(backends, dict):
            backends.pop(backend_id, None)
        self._provider_options = provider_options_from_config(self._llm_backends_config)
        self._refresh_provider_combo()
        self._refresh_backend_list()
        self._reload_provider_models()

    def _build_mcp_tab(self) -> None:
        tab = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)

        self._mcp_server_list = QtWidgets.QListWidget(tab)
        self._mcp_server_list.currentItemChanged.connect(self._on_mcp_server_changed)
        left_col.addWidget(self._mcp_server_list, 1)

        mcp_btn_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add")
        remove_btn = QtWidgets.QPushButton("Remove")
        add_btn.clicked.connect(self._on_add_mcp_server_clicked)
        remove_btn.clicked.connect(self._on_remove_mcp_server_clicked)
        mcp_btn_row.addWidget(add_btn)
        mcp_btn_row.addWidget(remove_btn)
        left_col.addLayout(mcp_btn_row)

        detail_scroll = QtWidgets.QScrollArea(tab)
        detail_scroll.setWidgetResizable(True)
        self._mcp_detail_container = QtWidgets.QWidget(detail_scroll)
        self._mcp_detail_layout = QtWidgets.QVBoxLayout(self._mcp_detail_container)
        self._mcp_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._mcp_detail_layout.setSpacing(8)
        self._mcp_detail_layout.addStretch(1)
        detail_scroll.setWidget(self._mcp_detail_container)

        servers = self._mcp_config.get("servers", {}) if isinstance(self._mcp_config, dict) else {}
        if isinstance(servers, dict):
            for server_id in sorted(servers.keys()):
                item = QtWidgets.QListWidgetItem(str(server_id))
                item.setData(QtCore.Qt.UserRole, server_id)
                self._mcp_server_list.addItem(item)

        if self._focused_server_id:
            self._mcp_server_list.hide()
        else:
            layout.addLayout(left_col, 0)

        layout.addWidget(detail_scroll, 1)
        if self._tabs is not None:
            self._tabs.addTab(tab, "MCP")

        if self._mcp_server_list.count() > 0:
            initial_id = self._focused_server_id or self._mcp_server_list.item(0).data(QtCore.Qt.UserRole)
            self._select_mcp_server(initial_id)
        else:
            self._render_mcp_server(None)

    # ---------- backend model discovery ----------

    def _active_provider_key(self) -> str:
        return active_provider_key(self._config)

    def _reload_provider_models(self) -> None:
        provider_key = self._active_provider_key()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            status = list_models_for_provider(self._llm_backends_config, provider_key)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        self._provider_model_status = status
        self._provider_models = set(status.models) if not status.error else None

        if status.error:
            label = status.provider_label or provider_key or "selected backend"
            self._show_banner(
                f"Could not query models for {label}.\n\n{status.error}"
            )
        else:
            self._hide_banner()

        self._refresh_langgraph_model_styles()
        self._refresh_action_buttons()

    def _on_provider_changed(self) -> None:
        widget = self._fields.get(("llm", "provider"))
        if not isinstance(widget, QtWidgets.QComboBox):
            return
        provider_key = str(widget.currentData() or "").strip()
        if not provider_key:
            return
        self._set_value_at_path(self._config, ("llm", "provider"), provider_key)
        self._reload_provider_models()

    def _show_banner(self, text: str) -> None:
        if not self._banner_label:
            return
        self._banner_label.setText(text)
        self._banner_label.setStyleSheet("font-weight: bold; color: #b00020;")
        self._banner_label.show()

    def set_banner_message(self, text: str) -> None:
        self._show_banner(text)

    def _hide_banner(self) -> None:
        if not self._banner_label:
            return
        self._banner_label.hide()
        self._banner_label.setText("")
        self._banner_label.setStyleSheet("")

    def _refresh_action_buttons(self) -> None:
        active_backend_exists = self._backend_cfg(self._active_provider_key()) is not None
        can_apply = active_backend_exists and self._provider_models is not None and not missing_required_roles(self._config, self._provider_models)
        for button in (getattr(self, "save_button", None), getattr(self, "apply_button", None)):
            if isinstance(button, QtWidgets.QPushButton):
                button.setEnabled(can_apply)

    def _refresh_provider_combo(self) -> None:
        widget = self._fields.get(("llm", "provider"))
        if not isinstance(widget, QtWidgets.QComboBox):
            return
        current_key = self._active_provider_key()
        widget.blockSignals(True)
        widget.clear()
        for index, option in enumerate(self._provider_options):
            widget.addItem(option.display_name, option.key)
            widget.setItemData(index, option.tooltip, QtCore.Qt.ToolTipRole)
        idx = widget.findData(current_key)
        if idx >= 0:
            widget.setCurrentIndex(idx)
        widget.blockSignals(False)

    def _refresh_langgraph_model_styles(self) -> None:
        models = self._provider_models
        status = self._provider_model_status

        for path, widget in self._fields.items():
            if not self._is_langgraph_node_model_path(path):
                continue
            if not isinstance(widget, QtWidgets.QLabel):
                continue

            configured = self._get_value_at_path(self._config, path)
            configured_str = "" if configured is None else str(configured).strip()

            if not configured_str:
                widget.setStyleSheet("font-weight: bold; color: #b00020;")
                widget.setToolTip("Required model is not configured")
            elif models is None:
                widget.setStyleSheet("font-weight: bold; color: #b00020;")
                detail = status.error if status is not None and status.error else "Model list is unavailable."
                widget.setToolTip(detail)
            elif configured_str not in models:
                provider_label = status.provider_label if status is not None else self._active_provider_key()
                widget.setStyleSheet("font-weight: bold; color: #b00020;")
                widget.setToolTip(f"Configured model not found for {provider_label}")
            else:
                widget.setStyleSheet("")
                widget.setToolTip("")

    # ---------- model picking ----------

    def _on_change_langgraph_node_model_clicked(self, path: tuple) -> None:
        # path shape: ("llm", "roles", "<role>", "model")
        role_name = path[2]

        if not self._provider_models:
            provider_label = self._active_provider_key() or "selected backend"
            QtWidgets.QMessageBox.warning(
                self,
                "Models unavailable",
                f"Model list is not available for {provider_label}. Fix the backend configuration "
                "and ensure its model-list endpoint is reachable.",
            )
            return

        current = self._get_value_at_path(self._config, path)
        current_str = "" if current is None else str(current).strip()

        status = self._provider_model_status
        provider_label = status.provider_label if status is not None else self._active_provider_key()
        models_sorted = sorted(self._provider_models)
        dlg = ModelPickerDialog(
            self,
            title=f"Select model for role: {role_name} ({provider_label})",
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
        self._refresh_action_buttons()

    # ---------- value handling ----------

    def _load_values(self):
        for path, widget in self._fields.items():
            value = self._get_value_at_path(self._config, path)

            if isinstance(widget, QtWidgets.QComboBox) and self._is_provider_path(path):
                provider_key = "" if value is None else str(value).strip()
                idx = widget.findData(provider_key)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                continue

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
        self._refresh_action_buttons()

    def _load_mcp_values(self, server_id: str) -> None:
        server_cfg = self._server_cfg(server_id, runtime=False)
        if not isinstance(server_cfg, dict):
            return

        label_edit = self._mcp_field_edits.get("label")
        enabled_box = self._mcp_field_edits.get("enabled")
        transport_type_edit = self._mcp_field_edits.get("transport.type")
        transport_url_edit = self._mcp_field_edits.get("transport.url")
        transport_headers_edit = self._mcp_field_edits.get("transport.headers")

        transport = server_cfg.get("transport", {}) or {}
        if not isinstance(transport, dict):
            transport = {}

        if isinstance(label_edit, QtWidgets.QLineEdit):
            label_edit.setText(str(server_cfg.get("label") or server_id))
        if isinstance(enabled_box, QtWidgets.QCheckBox):
            enabled_box.setChecked(bool(server_cfg.get("enabled", False)))
        if isinstance(transport_type_edit, QtWidgets.QLineEdit):
            transport_type_edit.setText(str(transport.get("type") or ""))
        if isinstance(transport_url_edit, QtWidgets.QLineEdit):
            transport_url_edit.setText(str(transport.get("url") or ""))
        if isinstance(transport_headers_edit, QtWidgets.QPlainTextEdit):
            headers = transport.get("headers", {}) or {}
            text = json.dumps(headers if isinstance(headers, dict) else {}, ensure_ascii=False, indent=2)
            transport_headers_edit.setPlainText(text)

        tools = server_cfg.get("tools", {}) or {}
        if not isinstance(tools, dict):
            tools = {}
        for tool_name, combo in self._tool_approval_boxes.items():
            if tool_name[0] != server_id:
                continue
            tool_cfg = tools.get(tool_name[1], {}) or {}
            approval = str(tool_cfg.get("approval") or "ask")
            idx = combo.findData(approval)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _apply_mcp_server_changes(self, server_id: str) -> None:
        server_cfg = self._server_cfg(server_id, runtime=False)
        if not isinstance(server_cfg, dict):
            return

        transport = server_cfg.get("transport", {}) or {}
        if not isinstance(transport, dict):
            transport = {}
            server_cfg["transport"] = transport

        label_edit = self._mcp_field_edits.get("label")
        enabled_box = self._mcp_field_edits.get("enabled")
        transport_type_edit = self._mcp_field_edits.get("transport.type")
        transport_url_edit = self._mcp_field_edits.get("transport.url")
        transport_headers_edit = self._mcp_field_edits.get("transport.headers")

        if isinstance(label_edit, QtWidgets.QLineEdit):
            server_cfg["label"] = label_edit.text().strip() or server_id
        if isinstance(enabled_box, QtWidgets.QCheckBox):
            server_cfg["enabled"] = bool(enabled_box.isChecked())
        if isinstance(transport_type_edit, QtWidgets.QLineEdit):
            transport["type"] = transport_type_edit.text().strip()
        if isinstance(transport_url_edit, QtWidgets.QLineEdit):
            transport["url"] = transport_url_edit.text().strip()
        if isinstance(transport_headers_edit, QtWidgets.QPlainTextEdit):
            raw = transport_headers_edit.toPlainText().strip()
            headers = transport.get("headers", {}) or {}
            try:
                parsed = json.loads(raw) if raw else {}
                headers = parsed if isinstance(parsed, dict) else headers
            except Exception:
                headers = headers if isinstance(headers, dict) else {}
            transport["headers"] = headers

        tools = server_cfg.get("tools", {}) or {}
        if not isinstance(tools, dict):
            tools = {}
            server_cfg["tools"] = tools

        for (row_server_id, tool_name), combo in self._tool_approval_boxes.items():
            if row_server_id != server_id:
                continue
            tool_cfg = tools.get(tool_name, {}) or {}
            if not isinstance(tool_cfg, dict):
                tool_cfg = {}
                tools[tool_name] = tool_cfg
            tool_cfg["approval"] = str(combo.currentData() or "ask")

    def _server_cfg(self, server_id: str, *, runtime: bool) -> dict | None:
        root = self._mcp_runtime_config if runtime else self._mcp_config
        servers = root.get("servers", {}) if isinstance(root, dict) else {}
        if not isinstance(servers, dict):
            return None
        server_cfg = servers.get(server_id)
        return server_cfg if isinstance(server_cfg, dict) else None

    def _select_mcp_server(self, server_id: str | None) -> None:
        if not server_id or self._mcp_server_list is None:
            return
        for idx in range(self._mcp_server_list.count()):
            item = self._mcp_server_list.item(idx)
            if str(item.data(QtCore.Qt.UserRole) or "") == server_id:
                self._mcp_server_list.setCurrentRow(idx)
                return
        self._render_mcp_server(server_id)

    def _show_focused_server(self, server_id: str) -> None:
        if self._tabs is not None:
            self._tabs.setCurrentIndex(1)
        self._select_mcp_server(server_id)

    def _on_add_mcp_server_clicked(self) -> None:
        servers = self._mcp_config.setdefault("servers", {})
        if not isinstance(servers, dict):
            servers = {}
            self._mcp_config["servers"] = servers
        base = "server"
        i = 1
        server_id = f"{base}_{i}"
        while server_id in servers:
            i += 1
            server_id = f"{base}_{i}"
        servers[server_id] = {
            "label": f"Server {i}",
            "enabled": False,
            "transport": {"type": "streamable-http", "url": "", "headers": {}},
            "status": {"available": False, "last_startup_check": None, "last_error": None},
            "tools": {},
        }
        if self._mcp_server_list is not None:
            item = QtWidgets.QListWidgetItem(server_id)
            item.setData(QtCore.Qt.UserRole, server_id)
            self._mcp_server_list.addItem(item)
            self._mcp_server_list.setCurrentItem(item)

    def _on_remove_mcp_server_clicked(self) -> None:
        if self._mcp_server_list is None or self._mcp_server_list.currentItem() is None:
            return
        item = self._mcp_server_list.currentItem()
        server_id = str(item.data(QtCore.Qt.UserRole) or "")
        if not server_id:
            return
        servers = self._mcp_config.get("servers", {})
        if isinstance(servers, dict):
            servers.pop(server_id, None)
        row = self._mcp_server_list.row(item)
        self._mcp_server_list.takeItem(row)
        if self._mcp_server_list.count() > 0:
            self._mcp_server_list.setCurrentRow(max(0, min(row, self._mcp_server_list.count() - 1)))
        else:
            self._render_mcp_server(None)

    def _on_mcp_server_changed(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None) -> None:
        if previous is not None:
            previous_id = str(previous.data(QtCore.Qt.UserRole) or "")
            if previous_id:
                self._apply_mcp_server_changes(previous_id)

        current_id = str(current.data(QtCore.Qt.UserRole) or "") if current is not None else None
        self._render_mcp_server(current_id)

    def _clear_mcp_detail(self) -> None:
        if self._mcp_detail_layout is None:
            return
        while self._mcp_detail_layout.count():
            item = self._mcp_detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._mcp_field_edits = {}
        self._tool_approval_boxes = {}

    def _render_mcp_server(self, server_id: str | None) -> None:
        self._clear_mcp_detail()
        if self._mcp_detail_layout is None:
            return

        if not server_id:
            self._mcp_detail_layout.addWidget(QtWidgets.QLabel("No MCP server selected."))
            self._mcp_detail_layout.addStretch(1)
            return

        server_cfg = self._server_cfg(server_id, runtime=False)
        runtime_server_cfg = self._server_cfg(server_id, runtime=True)
        if not isinstance(server_cfg, dict):
            self._mcp_detail_layout.addWidget(QtWidgets.QLabel("Server not found."))
            self._mcp_detail_layout.addStretch(1)
            return

        header = QtWidgets.QLabel(str(server_cfg.get("label") or server_id))
        font = header.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        header.setFont(font)
        self._mcp_detail_layout.addWidget(header)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        enabled_box = QtWidgets.QCheckBox("Enabled")
        self._mcp_field_edits["enabled"] = enabled_box
        form.addRow("", enabled_box)

        label_edit = QtWidgets.QLineEdit()
        self._mcp_field_edits["label"] = label_edit
        form.addRow("Label", label_edit)

        transport_type_edit = QtWidgets.QLineEdit()
        self._mcp_field_edits["transport.type"] = transport_type_edit
        form.addRow("Transport type", transport_type_edit)

        transport_url_edit = QtWidgets.QLineEdit()
        self._mcp_field_edits["transport.url"] = transport_url_edit
        form.addRow("Transport URL", transport_url_edit)

        transport_headers_edit = QtWidgets.QPlainTextEdit()
        transport_headers_edit.setMinimumHeight(100)
        self._mcp_field_edits["transport.headers"] = transport_headers_edit
        form.addRow("Transport headers", transport_headers_edit)

        self._mcp_detail_layout.addLayout(form)

        status_cfg = runtime_server_cfg if isinstance(runtime_server_cfg, dict) else server_cfg
        status = status_cfg.get("status", {}) or {}
        status_lines: list[str] = []
        if isinstance(status, dict):
            status_lines.append(f"Availability: {status.get('available')!r}")
            if status.get("last_startup_check"):
                status_lines.append(f"Last startup check: {status.get('last_startup_check')}")
            if status.get("last_error"):
                status_lines.append(f"Last error: {status.get('last_error')}")
        status_label = QtWidgets.QLabel("\n".join(status_lines) if status_lines else "No status recorded.")
        status_label.setWordWrap(True)
        self._mcp_detail_layout.addWidget(status_label)

        tools_group = QtWidgets.QGroupBox("Discovered tools")
        tools_layout = QtWidgets.QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(8, 8, 8, 8)
        tools_layout.setSpacing(6)

        runtime_tools = status_cfg.get("tools", {}) or {}
        if not isinstance(runtime_tools, dict):
            runtime_tools = {}
        persisted_tools = server_cfg.get("tools", {}) or {}
        if not isinstance(persisted_tools, dict):
            persisted_tools = {}

        tool_names = sorted(set(runtime_tools.keys()) | set(persisted_tools.keys()))
        if tool_names:
            for tool_name in tool_names:
                runtime_tool_cfg = runtime_tools.get(tool_name) if isinstance(runtime_tools.get(tool_name), dict) else {}
                persisted_tool_cfg = persisted_tools.get(tool_name, {}) if isinstance(persisted_tools.get(tool_name), dict) else {}
                if not isinstance(persisted_tool_cfg, dict):
                    persisted_tool_cfg = {}

                row = QtWidgets.QFrame()
                row_layout = QtWidgets.QGridLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setHorizontalSpacing(8)
                row_layout.setVerticalSpacing(4)

                name_label = QtWidgets.QLabel(tool_name)
                name_font = name_label.font()
                name_font.setBold(True)
                name_label.setFont(name_font)
                row_layout.addWidget(name_label, 0, 0)

                availability = bool(runtime_tool_cfg.get("available", persisted_tool_cfg.get("available", False)))
                available_label = QtWidgets.QLabel("available" if availability else "unavailable")
                row_layout.addWidget(available_label, 0, 1)

                approval_box = QtWidgets.QComboBox()
                approval_box.addItem("ask", "ask")
                approval_box.addItem("auto", "auto")
                approval_box.addItem("deny", "deny")
                self._tool_approval_boxes[(server_id, tool_name)] = approval_box
                row_layout.addWidget(QtWidgets.QLabel("Approval"), 1, 0)
                row_layout.addWidget(approval_box, 1, 1)

                tools_layout.addWidget(row)
        else:
            tools_layout.addWidget(QtWidgets.QLabel("No tools discovered for this server."))

        self._mcp_detail_layout.addWidget(tools_group)
        self._mcp_detail_layout.addStretch(1)
        self._load_mcp_values(server_id)

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

        Additionally: enforce that required fields (like answer) are never
        accidentally cleared by restoring from the original config snapshot.
        """
        new_cfg = json.loads(json.dumps(self._config))

        for path, widget in self._fields.items():
            old_value = self._get_value_at_path(new_cfg, path)

            if self._is_provider_path(path) and isinstance(widget, QtWidgets.QComboBox):
                self._set_value_at_path(new_cfg, path, str(widget.currentData() or "").strip())
                continue

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
        for role_name in ("planner", "reflect"):
            role_path = ("llm", "roles", role_name, "model")
            orig_model = self._get_value_at_path(self._orig_config, role_path)
            cur_model = self._get_value_at_path(new_cfg, role_path)
            if (not isinstance(cur_model, str)) or (not cur_model.strip()):
                if isinstance(orig_model, str) and orig_model.strip():
                    self._set_value_at_path(new_cfg, role_path, orig_model)

        self._config = new_cfg
        if self._backend_list is not None and self._backend_list.currentItem() is not None:
            current_backend = str(self._backend_list.currentItem().data(QtCore.Qt.UserRole) or "")
            if current_backend:
                self._apply_backend_changes(current_backend)
        self._provider_options = provider_options_from_config(self._llm_backends_config)
        self._refresh_provider_combo()
        self._reload_provider_models()
        current_server = None
        if self._mcp_server_list is not None and self._mcp_server_list.currentItem() is not None:
            current_server = str(self._mcp_server_list.currentItem().data(QtCore.Qt.UserRole) or "")
        elif self._focused_server_id:
            current_server = self._focused_server_id
        if current_server:
            self._apply_mcp_server_changes(current_server)

    # ---------- validation ----------

    def _validate_required(self) -> bool:
        backends = self._llm_backends_config.get("backends", {}) if isinstance(self._llm_backends_config, dict) else {}
        if not isinstance(backends, dict) or not backends:
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid backend registry",
                "At least one backend must exist.",
            )
            return False
        for backend_id, backend_cfg in backends.items():
            if not isinstance(backend_cfg, dict):
                continue
            if not str(backend_cfg.get("kind") or "").strip():
                QtWidgets.QMessageBox.critical(
                    self,
                    "Invalid backend",
                    f"Backend '{backend_id}' is missing a connection type.",
                )
                return False
            if not str(backend_cfg.get("url") or "").strip():
                QtWidgets.QMessageBox.critical(
                    self,
                    "Invalid backend",
                    f"Backend '{backend_id}' is missing a base URL.",
                )
                return False
        if self._backend_cfg(self._active_provider_key()) is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid backend",
                "The selected active backend does not exist in the backend registry.",
            )
            return False
        missing_roles = missing_required_roles(self._config, self._provider_models)
        if self._provider_models is None:
            detail = self._provider_model_status.error if self._provider_model_status is not None else "Unknown backend error."
            QtWidgets.QMessageBox.critical(
                self,
                "Backend models unavailable",
                f"Could not validate models for the selected backend.\n\n{detail}",
            )
            return False

        for role_name in ("planner", "reflect"):
            model = self._get_value_at_path(self._config, ("llm", "roles", role_name, "model"))
            if isinstance(model, str) and model.strip():
                continue
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid config",
                f"llm.roles.{role_name}.model is required and cannot be empty.",
            )
            return False
        if missing_roles:
            missing_text = ", ".join(missing_roles)
            provider_label = self._provider_model_status.provider_label if self._provider_model_status is not None else self._active_provider_key()
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid backend models",
                f"The selected backend ({provider_label}) does not provide the configured required role models.\n\n"
                f"Missing roles: {missing_text}",
            )
            return False
        return True

    # ---------- button handlers ----------

    def _on_save_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
        self.llmBackendsApplied.emit(self._llm_backends_config)
        self.mcpConfigApplied.emit(self._mcp_config)
        self.accept()

    def _on_apply_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
        self.llmBackendsApplied.emit(self._llm_backends_config)
        self.mcpConfigApplied.emit(self._mcp_config)
