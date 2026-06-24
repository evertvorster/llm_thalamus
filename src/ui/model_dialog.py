"""ModelPickerDialog — select a model and configure scoped models for cycling."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ModelPickerDialog(QtWidgets.QDialog):
    """A dialog listing available models grouped by provider.

    Each model row has a checkbox to mark it as "scoped" (enabled for
    Ctrl+P cycling).  A filter at the top narrows by model name or
    provider.  On accept, the caller reads :attr:`selected_model_id`,
    :attr:`selected_provider`, and :attr:`scoped_ids`.

    Usage::

        dlg = ModelPickerDialog(models, scoped_ids, parent=self)
        if dlg.exec() == QDialog.Accepted:
            bridge.send_command({
                "type": "set_model",
                "provider": dlg.selected_provider,
                "modelId": dlg.selected_model_id,
            })
            # save dlg.scoped_ids() to QSettings
    """

    def __init__(
        self,
        models: list[dict],
        scoped_ids: set[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Model")
        self.resize(480, 480)
        self.setMinimumWidth(420)

        self._models = models
        self._scoped_ids: set[str] = set(scoped_ids)
        self._selected_model_id: str | None = None
        self._selected_provider: str | None = None

        layout = QtWidgets.QVBoxLayout(self)

        # ── filter ─────────────────────────────────────────────
        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("Filter by name or provider…")
        self._filter.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter)

        # ── tree ───────────────────────────────────────────────
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #ccc; }"
            "QTreeWidget::item { padding: 2px 4px; }"
        )
        layout.addWidget(self._tree, 1)

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

        self._build_tree()
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

    @property
    def scoped_ids(self) -> set[str]:
        """The set of model IDs marked as scoped."""
        return self._scoped_ids.copy()

    # ── tree construction ─────────────────────────────────────────

    def _build_tree(self) -> None:
        self._tree.clear()

        # Group by provider.
        by_provider: dict[str, list[dict]] = {}
        for m in self._models:
            pid = m.get("id", "")
            prov = m.get("provider", "?")
            name = m.get("name") or pid or "?"
            ctx = m.get("contextWindow", 0) or 0
            by_provider.setdefault(prov, []).append(
                {"id": pid, "name": name, "provider": prov, "contextWindow": ctx}
            )

        for prov in sorted(by_provider.keys(), key=str.lower):
            models = by_provider[prov]

            # Provider header — bold, non-checkable.
            header = QtWidgets.QTreeWidgetItem([prov])
            fnt = header.font(0)
            fnt.setBold(True)
            header.setFont(0, fnt)
            header.setFlags(
                header.flags()
                & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable
                & ~QtCore.Qt.ItemFlag.ItemIsSelectable
            )
            header.setData(0, QtCore.Qt.ItemDataRole.UserRole, {"kind": "provider"})
            self._tree.addTopLevelItem(header)

            for m in sorted(models, key=lambda x: x["name"].lower()):
                ctx_str = f"{m['contextWindow'] // 1000}K" if m["contextWindow"] else "?"
                label = f"  {m['name']}  ({ctx_str} ctx)"

                item = QtWidgets.QTreeWidgetItem([label])
                item.setFlags(
                    item.flags()
                    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    0,
                    QtCore.Qt.CheckState.Checked
                    if m["id"] in self._scoped_ids
                    else QtCore.Qt.CheckState.Unchecked,
                )
                item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {"kind": "model", "id": m["id"], "provider": m["provider"]},
                )
                header.addChild(item)

        # Expand all provider groups.
        for i in range(self._tree.topLevelItemCount()):
            self._tree.expandItem(self._tree.topLevelItem(i))

    # ── filter ────────────────────────────────────────────────────

    def _on_filter_changed(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            prov_item = self._tree.topLevelItem(i)
            visible_children = 0
            for j in range(prov_item.childCount()):
                child = prov_item.child(j)
                data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict):
                    continue
                name = data.get("name", "").lower()
                provider = data.get("provider", "").lower()
                match = (
                    not needle
                    or needle in name
                    or needle in provider
                )
                child.setHidden(not match)
                if match:
                    visible_children += 1
            prov_item.setHidden(visible_children == 0)

    # ── accept ────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        # Collect scoped model IDs from checkbox state.
        self._scoped_ids.clear()
        for i in range(self._tree.topLevelItemCount()):
            prov_item = self._tree.topLevelItem(i)
            for j in range(prov_item.childCount()):
                child = prov_item.child(j)
                data = child.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(data, dict) or data.get("kind") != "model":
                    continue
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    self._scoped_ids.add(data["id"])

        # Use the currently selected item, or the first visible model.
        current = self._tree.currentItem()
        if current is not None:
            data = current.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("kind") == "model":
                self._selected_model_id = data["id"]
                self._selected_provider = data["provider"]

        if self._selected_model_id is None:
            # Fallback: first visible model in the tree.
            for i in range(self._tree.topLevelItemCount()):
                prov_item = self._tree.topLevelItem(i)
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
