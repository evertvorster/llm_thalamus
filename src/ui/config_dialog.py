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
    mcpConfigApplied = QtCore.Signal(dict)

    _META_SECTION_KEYS = {"ui_descriptions"}

    def __init__(
        self,
        config: dict,
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
        self._orig_mcp_config = json.loads(json.dumps(mcp_config))
        self._mcp_config = json.loads(json.dumps(mcp_config))
        self._mcp_runtime_config = json.loads(
            json.dumps(mcp_runtime_config if isinstance(mcp_runtime_config, dict) else mcp_config)
        )
        self._focused_server_id = focused_server_id if isinstance(focused_server_id, str) else None

        self._fields: dict[tuple, QtWidgets.QWidget] = {}
        self._mcp_field_edits: dict[str, QtWidgets.QWidget] = {}
        self._tool_approval_boxes: dict[tuple[str, str], QtWidgets.QComboBox] = {}

        self._ollama_models: set[str] | None = None
        self._ollama_list_error: str | None = None

        self._banner_label: QtWidgets.QLabel | None = None
        self._tabs: QtWidgets.QTabWidget | None = None
        self._general_scroll: QtWidgets.QScrollArea | None = None
        self._mcp_server_list: QtWidgets.QListWidget | None = None
        self._mcp_detail_container: QtWidgets.QWidget | None = None
        self._mcp_detail_layout: QtWidgets.QVBoxLayout | None = None

        self._build_ui()
        self._load_values()
        self._start_ollama_list()

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

        self._tabs = QtWidgets.QTabWidget(self)
        main_layout.addWidget(self._tabs, 1)

        self._build_general_tab()
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

    def _build_mcp_tab(self) -> None:
        tab = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._mcp_server_list = QtWidgets.QListWidget(tab)
        self._mcp_server_list.currentItemChanged.connect(self._on_mcp_server_changed)

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
            layout.addWidget(self._mcp_server_list, 0)

        layout.addWidget(detail_scroll, 1)
        if self._tabs is not None:
            self._tabs.addTab(tab, "MCP")

        if self._mcp_server_list.count() > 0:
            initial_id = self._focused_server_id or self._mcp_server_list.item(0).data(QtCore.Qt.UserRole)
            self._select_mcp_server(initial_id)
        else:
            self._render_mcp_server(None)

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
        # path shape: ("llm", "roles", "<role>", "model")
        role_name = path[2]

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
            title=f"Select model for role: {role_name}",
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
        self._refresh_langgraph_model_styles()
        current_server = None
        if self._mcp_server_list is not None and self._mcp_server_list.currentItem() is not None:
            current_server = str(self._mcp_server_list.currentItem().data(QtCore.Qt.UserRole) or "")
        elif self._focused_server_id:
            current_server = self._focused_server_id
        if current_server:
            self._apply_mcp_server_changes(current_server)

    # ---------- validation ----------

    def _validate_required(self) -> bool:
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
        return True

    # ---------- button handlers ----------

    def _on_save_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
        self.mcpConfigApplied.emit(self._mcp_config)
        self.accept()

    def _on_apply_clicked(self):
        self._apply_changes_to_config()
        if not self._validate_required():
            return
        self.configApplied.emit(self._config, True)
        self.mcpConfigApplied.emit(self._mcp_config)
