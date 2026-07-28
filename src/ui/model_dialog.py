"""ModelPickerDialog — select a model from all or enabled model lists."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ModelPickerDialog(QtWidgets.QDialog):
    """A dialog listing available models with "All" and "Enabled" tabs.

    Each tab shows models grouped by provider.  A filter at the top
    narrows by model name or provider.  On accept, the caller reads
    :attr:`selected_model_id` and :attr:`selected_provider`.

    Usage::

        dlg = ModelPickerDialog(models, enabled_ids, parent=self)
        if dlg.exec() == QDialog.Accepted:
            bridge.send_command({
                "type": "set_model",
                "provider": dlg.selected_provider,
                "modelId": dlg.selected_model_id,
            })
    """

    def __init__(
        self,
        models: list[dict],
        enabled_ids: set[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Model")
        self.resize(480, 480)
        self.setMinimumWidth(420)

        self._models = models
        self._enabled_ids: set[str] = set(enabled_ids)
        self._selected_model_id: str | None = None
        self._selected_provider: str | None = None

        layout = QtWidgets.QVBoxLayout(self)

        # ── filter ─────────────────────────────────────────────
        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("Filter by name or provider…")
        self._filter.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter)

        # ── tabs ───────────────────────────────────────────────
        self._tabs = QtWidgets.QTabWidget()
        self._all_tree = self._build_tree(self._models, show_enabled_only=False)
        self._enabled_tree = self._build_tree(self._models, show_enabled_only=True)
        self._tabs.addTab(self._all_tree, "All")
        self._tabs.addTab(self._enabled_tree, "Enabled")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, 1)

        # ── buttons ────────────────────────────────────────────
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

        self._filter.setFocus()

    # ── public accessors ───────────────────────────────────────────

    @property
    def selected_model_id(self) -> str | None:
        """The ``id`` field of the selected model, or ``None`` if cancelled."""
        return self._selected_model_id

    @property
    def selected_provider(self) -> str | None:
        """The ``provider`` field of the selected model."""
        return self._selected_provider

    # ── public selection ────────────────────────────────────────────

    def select_model(self, model_id: str) -> None:
        """Programmatically select the tree item with *model_id*.

        Expands the parent provider group and scrolls to the item.
        Does nothing if *model_id* is not found in either tree.
        """
        for tree in (self._all_tree, self._enabled_tree):
            for i in range(tree.topLevelItemCount()):
                prov_item = tree.topLevelItem(i)
                for j in range(prov_item.childCount()):
                    child = prov_item.child(j)
                    data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if not isinstance(data, dict):
                        continue
                    if data.get("id") == model_id:
                        tree.setCurrentItem(child)
                        tree.expandItem(prov_item)
                        tree.scrollToItem(child)
                        return

    # ── tree construction ─────────────────────────────────────────

    def _build_tree(
        self, models: list[dict], show_enabled_only: bool
    ) -> QtWidgets.QTreeWidget:
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(12)
        tree.setAnimated(True)
        tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #ccc; }"
            "QTreeWidget::item { padding: 2px 4px; }"
        )
        tree.itemClicked.connect(self._on_item_clicked)

        # Group by provider.
        by_provider: dict[str, list[dict]] = {}
        for m in models:
            pid = m.get("id", "")
            if show_enabled_only and pid not in self._enabled_ids:
                continue
            prov = m.get("provider", "?")
            name = m.get("name") or pid or "?"
            ctx = m.get("contextWindow", 0) or 0
            by_provider.setdefault(prov, []).append(
                {"id": pid, "name": name, "provider": prov, "contextWindow": ctx}
            )

        for prov in sorted(by_provider.keys(), key=str.lower):
            group = by_provider[prov]

            # Provider header — bold, non-selectable.
            header = QtWidgets.QTreeWidgetItem([prov])
            fnt = header.font(0)
            fnt.setBold(True)
            header.setFont(0, fnt)
            header.setFlags(header.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            header.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"kind": "provider"})
            tree.addTopLevelItem(header)

            for m in sorted(group, key=lambda x: x["name"].lower()):
                ctx_str = (
                    f"{m['contextWindow'] // 1000}K" if m["contextWindow"] else "?"
                )
                label = f"  {m['name']}  ({ctx_str} ctx)"

                item = QtWidgets.QTreeWidgetItem([label])
                item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {
                        "kind": "model",
                        "id": m["id"],
                        "provider": m["provider"],
                        "name": m["name"],
                    },
                )
                header.addChild(item)

        # Expand all provider groups.
        for i in range(tree.topLevelItemCount()):
            tree.expandItem(tree.topLevelItem(i))

        return tree

    # ── filter ────────────────────────────────────────────────────

    def _current_tree(self) -> QtWidgets.QTreeWidget:
        """Return the tree widget for the currently active tab."""
        return self._tabs.currentWidget()  # type: ignore[return-value]

    def _on_filter_changed(self, text: str) -> None:
        needle = text.strip().lower()
        tree = self._current_tree()
        for i in range(tree.topLevelItemCount()):
            prov_item = tree.topLevelItem(i)
            visible_children = 0
            for j in range(prov_item.childCount()):
                child = prov_item.child(j)
                data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict):
                    continue
                name = data.get("name", "").lower()
                provider = data.get("provider", "").lower()
                match = not needle or needle in name or needle in provider
                child.setHidden(not match)
                if match:
                    visible_children += 1
            prov_item.setHidden(visible_children == 0)

    def _on_tab_changed(self, index: int) -> None:
        """Re-apply the current filter text when switching tabs."""
        self._on_filter_changed(self._filter.text())

    def _on_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("kind") == "model":
            self._selected_model_id = data["id"]
            self._selected_provider = data["provider"]

    # ── accept ────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        # Use the currently selected item in the active tree, or first visible model.
        tree = self._current_tree()
        current = tree.currentItem()
        if current is not None:
            data = current.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "model":
                self._selected_model_id = data["id"]
                self._selected_provider = data["provider"]

        if self._selected_model_id is None:
            # Fallback: first visible model in the active tree.
            for i in range(tree.topLevelItemCount()):
                prov_item = tree.topLevelItem(i)
                for j in range(prov_item.childCount()):
                    child = prov_item.child(j)
                    if child.isHidden():
                        continue
                    data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if isinstance(data, dict) and data.get("kind") == "model":
                        self._selected_model_id = data["id"]
                        self._selected_provider = data["provider"]
                        break
                if self._selected_model_id:
                    break

        self.accept()
