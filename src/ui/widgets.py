from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


# Shared zoom state for the chat input font size.
_input_zoom: float = 1.0
_base_input_size: int = 0  # set once on first zoom


class ChatInput(QtWidgets.QPlainTextEdit):
    """
    Chat input widget:
      - Enter/Return sends
      - Shift+Enter inserts newline
    """
    sendRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.setFont(mono_font)
        self.setPlaceholderText("Type a message…")
        self.setTabChangesFocus(False)
        global _base_input_size, _input_zoom
        if _base_input_size == 0:
            p = self.font().pointSize()
            _base_input_size = p if p > 0 else 14
        # Restore saved zoom.
        settings = QtCore.QSettings("llm-thalamus", "llm-thalamus")
        saved = settings.value("input/zoom")
        if saved is not None:
            try:
                _input_zoom = float(saved)
            except (ValueError, TypeError):
                _input_zoom = 1.0
        self._apply_zoom()
        self.set_thinking_border_color("off")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source: QtCore.QMimeData) -> None:
        """Intercept paste to capture image data."""
        if source.hasImage():
            img = QtGui.QImage(source.imageData())
            if not img.isNull():
                # Save to attachments directory
                import os
                from pathlib import Path
                attach_dir = Path.home() / ".pi" / "agent" / "sessions" / "attachments"
                attach_dir.mkdir(parents=True, exist_ok=True)
                ts = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd_hh-mm-ss")
                out_path = str(attach_dir / f"pasted-image-{ts}.png")
                img.save(out_path, "PNG")
                # Find the parent AttachmentBar
                parent = self.parent()
                while parent is not None and not hasattr(parent, "add_dropped_file"):
                    parent = parent.parent()
                if parent is not None and hasattr(parent, "add_dropped_file"):
                    parent.add_dropped_file(out_path)
                return
        super().insertFromMimeData(source)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            global _input_zoom
            delta = event.angleDelta().y()
            _input_zoom = max(0.5, min(3.0, _input_zoom + (0.1 if delta > 0 else -0.1)))
            self._apply_zoom()
            # Persist zoom.
            QtCore.QSettings("llm-thalamus", "llm-thalamus").setValue("input/zoom", _input_zoom)
            event.accept()
        else:
            super().wheelEvent(event)

    _THINKING_COLORS = {
        "off": "#888888",
        "minimal": "#4caf50",
        "low": "#2196f3",
        "medium": "#ff9800",
        "high": "#f44336",
        "xhigh": "#9c27b0",
    }

    def set_thinking_border_color(self, level: str) -> None:
        """Set the input border color to indicate thinking level."""
        color = self._THINKING_COLORS.get(level, "#888888")
        self.setStyleSheet(
            f"QPlainTextEdit {{ border: 2px solid {color}; border-radius: 4px; padding: 4px; }}"
        )

    def _apply_zoom(self):
        fs = max(8, int(_base_input_size * _input_zoom))
        f = self.font()
        f.setPointSize(fs)
        self.setFont(f)

    # ── drag-and-drop ────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if not urls:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        # Find the parent AttachmentBar to add the file
        parent = self.parent()
        while parent and not hasattr(parent, 'add_dropped_file'):
            parent = parent.parent()
        if parent and hasattr(parent, 'add_dropped_file'):
            for url in urls:
                parent.add_dropped_file(url.toLocalFile())

    # ── clipboard paste (images) handled in insertFromMimeData ──


class BrainWidget(QtWidgets.QLabel):
    """
    Brain display widget with three states:
      - 'inactive'  -> everything dark
      - 'thalamus'  -> only brainstem/thalamus lit
      - 'llm'       -> whole brain lit

    Supports a "saturation" factor used by the UI while model thinking is active.
    This is exposed as a real Qt property so we can smoothly animate it.
    """

    clicked = QtCore.Signal()
    transitionChanged = QtCore.Signal(float)
    saturationChanged = QtCore.Signal(float)

    def __init__(self, graphics_dir: Path, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("background-color: black;")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

        self._images_dir: Path = Path(graphics_dir)

        self._pixmaps: dict[str, QtGui.QPixmap] = {
            "inactive": self._load_pixmap("inactive.jpg"),
            "thalamus": self._load_pixmap("thalamus.jpg"),
            "llm": self._load_pixmap("llm.jpg"),
        }

        self._state: str = "inactive"

        self._from_state: str | None = None
        self._transition: float = 1.0
        self._animating: bool = False

        # Saturation factor (1.0 = unchanged). Cache only exact factors used.
        self._saturation: float = 1.0
        self._sat_cache: dict[tuple[int, int], QtGui.QPixmap] = {}
        # key: (pixmap_cache_key, saturation_pct) -> QPixmap

        self._anim = QtCore.QPropertyAnimation(self, b"transition")
        self._anim.setDuration(1000)
        self._anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    # --- QProperty: transition -------------------------------------------------

    def getTransition(self) -> float:
        return self._transition

    def setTransition(self, value: float) -> None:
        self._transition = float(value)
        self.transitionChanged.emit(self._transition)
        self.update()

    transition = QtCore.Property(
        float, fget=getTransition, fset=setTransition, notify=transitionChanged
    )

    # --- QProperty: saturation -------------------------------------------------

    def getSaturation(self) -> float:
        return self._saturation

    def setSaturation(self, value: float) -> None:
        """
        Qt property setter. Intended for smooth animations.
        """
        v = float(value)
        if v < 0.0:
            v = 0.0
        if v > 2.0:
            v = 2.0
        v = round(v, 2)

        if v == self._saturation:
            return

        self._saturation = v
        self.saturationChanged.emit(self._saturation)
        self.update()

    saturation = QtCore.Property(
        float, fget=getSaturation, fset=setSaturation, notify=saturationChanged
    )

    # Back-compat helper used by older UI code
    def set_saturation(self, value: float) -> None:
        self.setSaturation(value)

    def get_saturation(self) -> float:
        return self.getSaturation()

    # --- state handling --------------------------------------------------------

    def _load_pixmap(self, name: str) -> QtGui.QPixmap:
        p = self._images_dir / name
        pm = QtGui.QPixmap(str(p))
        return pm

    def set_state(self, state: str) -> None:
        if state == self._state:
            return

        self._from_state = self._state
        self._state = state

        # animate transition between images
        self._animating = True
        self._anim.stop()
        self._transition = 0.0
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        self._animating = False
        self._from_state = None
        self._transition = 1.0
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # --- rendering -------------------------------------------------------------

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("black"))

        target = self._pixmaps.get(self._state)
        if target is None or target.isNull():
            return

        if self._animating and self._from_state:
            src = self._pixmaps.get(self._from_state)
            if src and not src.isNull():
                t = max(0.0, min(1.0, self._transition))

                painter.setOpacity(1.0 - t)
                self._draw_pixmap_scaled(painter, src)

                painter.setOpacity(t)
                self._draw_pixmap_scaled(painter, target)

                painter.setOpacity(1.0)
                return

        self._draw_pixmap_scaled(painter, target)

    def _draw_pixmap_scaled(self, painter: QtGui.QPainter, pm: QtGui.QPixmap) -> None:
        if pm.isNull():
            return

        # Apply saturation effect (cached) BEFORE scaling.
        pm_eff = self._pixmap_with_saturation(pm, self._saturation)

        r = self.rect()
        scaled = pm_eff.scaled(
            r.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        x = (r.width() - scaled.width()) // 2
        y = (r.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def _pixmap_with_saturation(self, pm: QtGui.QPixmap, saturation: float) -> QtGui.QPixmap:
        if saturation == 1.0:
            return pm

        sat_pct = int(round(saturation * 100))
        key = (int(pm.cacheKey()), sat_pct)
        cached = self._sat_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached

        img = pm.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)

        # Adjust saturation in HSV space.
        w = img.width()
        h = img.height()
        for y in range(h):
            for x in range(w):
                c = QtGui.QColor.fromRgba(img.pixel(x, y))
                if c.alpha() == 0:
                    continue
                h_, s, v, a = c.getHsv()
                if h_ < 0:
                    continue
                s2 = int(max(0, min(255, round(s * saturation))))
                img.setPixelColor(x, y, QtGui.QColor.fromHsv(h_, s2, v, a))

        out = QtGui.QPixmap.fromImage(img)
        self._sat_cache[key] = out
        return out


class SessionListWidget(QtWidgets.QWidget):
    """
    Session list panel for the right sidebar — 4-level QTreeWidget.

    Tree structure::

        CWD (shortened path)               ← Level 1 – collapsible
        ├─ YYYY-MM-DD (count)              ← Level 2 – date group
        │   ├─ First user message…         ← Level 3 – session label
        │   │   ├─ agent-name              ← Level 4 – subagent fork
        │   │   └─ …
        │   └─ Another session…
        └─ …

    Current session is bold.  Session forks are detected via the
    ``parentSession`` header field.  Agent names are read from the
    parent session's ``subagent`` tool calls.

    Signals:
        new_session_requested:  The user wants a fresh session.
        switch_requested:       (session_path: str) Load a different session.
        rename_requested:       (session_path: str, new_name: str)
        delete_requested:       (session_path: str)
        inspect_requested:      (session_path: str) Open in a read‑only viewer.
    """

    _ITEM_KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
    _PATH_ROLE = QtCore.Qt.ItemDataRole.UserRole

    new_session_requested = QtCore.Signal()
    switch_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    delete_requested = QtCore.Signal(list)
    inspect_requested = QtCore.Signal(str)
    selected_session_changed = QtCore.Signal(object)  # str | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Sessions header ────────────────────────────────────
        header = QtWidgets.QLabel("Sessions")
        f = header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        header.setFont(f)
        layout.addWidget(header)

        # ── session tree ───────────────────────────────────────
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree, 1)

        self._current_path: str | None = None
        self._selected_item: QtWidgets.QTreeWidgetItem | None = None

    # ── public API ─────────────────────────────────────────────

    def set_sessions(
        self, session_dir: str | None, current_path: str | None
    ) -> None:
        """Populate the tree from all ``--*--/`` directories under *session_dir*.

        Each ``.jsonl`` file is parsed with :meth:`_parse_session_info`.
        Items are grouped: CWD → date → parent-session → fork.
        """
        self._tree.clear()
        self._current_path = current_path

        if not session_dir:
            self._tree.addTopLevelItem(
                QtWidgets.QTreeWidgetItem(["(no session dir)"])
            )
            return

        sdir = Path(session_dir)
        if not sdir.is_dir():
            self._tree.addTopLevelItem(
                QtWidgets.QTreeWidgetItem(["(session dir not found)"])
            )
            return

        # ── 1. scan everything ─────────────────────────────────
        parents: dict[str, dict] = {}  # path → info  (sessions w/o parentSession)
        forks: dict[str, list[dict]] = {}  # parent_path → [fork_info]
        cwd_sessions: dict[str, list[dict]] = {}  # cwd → [info, ...]

        for cwd_subdir in sorted(sdir.iterdir()):
            if not cwd_subdir.is_dir():
                continue
            for jsonl_file in sorted(cwd_subdir.iterdir()):
                if jsonl_file.suffix != ".jsonl":
                    continue
                info = self._parse_session_info(jsonl_file)
                if info is None:
                    continue

                cwd = info["cwd"]
                cwd_sessions.setdefault(cwd, []).append(info)

                parent = info.get("parent_session")
                if parent:
                    forks.setdefault(parent, []).append(info)
                else:
                    parents[info["path"]] = info

        if not cwd_sessions:
            self._tree.addTopLevelItem(
                QtWidgets.QTreeWidgetItem(["(no sessions)"])
            )
            return

        # ── 2. sort CWD keys: current CWD first ────────────────
        cwd_now = str(Path.cwd())
        cwd_keys = sorted(cwd_sessions.keys(), key=lambda c: (c != cwd_now, c))

        for cwd in cwd_keys:
            cwd_item = QtWidgets.QTreeWidgetItem(
                [self._format_cwd_label(cwd)]
            )
            cwd_item.setData(0, self._ITEM_KIND_ROLE, "cwd")
            cwd_item.setData(0, self._PATH_ROLE, cwd)
            self._tree.addTopLevelItem(cwd_item)

            # ── group by date ──────────────────────────────────
            infos = cwd_sessions[cwd]
            from collections import defaultdict

            by_date: dict[str, list[dict]] = defaultdict(list)
            for info in infos:
                ts = info.get("timestamp", "")
                date = ts[:10] if len(ts) >= 10 else "?"
                by_date[date].append(info)

            for date in sorted(by_date.keys(), reverse=True):
                day = by_date[date]
                date_item = QtWidgets.QTreeWidgetItem(
                    [self._format_date_label(date, len(day))]
                )
                fnt = date_item.font(0)
                fnt.setBold(True)
                date_item.setFont(0, fnt)
                date_item.setData(0, self._ITEM_KIND_ROLE, "date")
                cwd_item.addChild(date_item)

                # ── parents first, then attach forks ───────────
                day_parents = [
                    i for i in day if not i.get("parent_session")
                ]
                # newest-first within the day
                day_parents.sort(
                    key=lambda i: i.get("timestamp", ""), reverse=True
                )

                for pinfo in day_parents:
                    display = (
                        pinfo.get("first_message")
                        or Path(pinfo["path"]).stem
                    )[:80]
                    p_item = QtWidgets.QTreeWidgetItem([display])
                    p_item.setData(0, self._ITEM_KIND_ROLE, "session")
                    p_item.setData(0, self._PATH_ROLE, pinfo["path"])
                    date_item.addChild(p_item)

                    # ── forks of this parent ───────────────────
                    p_forks = forks.get(pinfo["path"], [])
                    p_forks.sort(
                        key=lambda fi: fi.get("timestamp", "")
                    )
                    for fi in p_forks:
                        agent = self._find_agent_name_for_fork(
                            fi["path"], pinfo["path"]
                        )
                        f_item = QtWidgets.QTreeWidgetItem([agent])
                        f_item.setData(0, self._ITEM_KIND_ROLE, "fork")
                        f_item.setData(
                            0,
                            self._PATH_ROLE,
                            fi["path"],
                        )
                        p_item.addChild(f_item)

                # ── orphan forks (parent not in this date group) ──
                orphan_forks = [
                    i
                    for i in day
                    if i.get("parent_session")
                    and i["parent_session"] not in parents
                ]
                for fi in orphan_forks:
                    display = (
                        fi.get("first_message")
                        or Path(fi["path"]).stem
                    )[:80]
                    f_item = QtWidgets.QTreeWidgetItem([display])
                    f_item.setData(0, self._ITEM_KIND_ROLE, "fork")
                    f_item.setData(
                        0,
                        self._PATH_ROLE, fi["path"]
                    )
                    date_item.addChild(f_item)

            # expand CWD that matches the current working dir
            if cwd == cwd_now:
                self._tree.expandItem(cwd_item)

        # Highlight the current session / fork via the standard path
        # so that _unbold_all() is guaranteed to run after any rebuild.
        self.set_current_session(self._current_path)

    def set_current_session(self, session_path: str | None) -> None:
        """Update which session / fork is highlighted."""
        self._current_path = session_path

        def _walk(item: QtWidgets.QTreeWidgetItem) -> bool:
            for i in range(item.childCount()):
                child = item.child(i)
                stored = child.data(0, self._PATH_ROLE)
                if stored and stored == session_path:
                    self._highlight_item(child)
                    self._ensure_visible(child)
                    return True
                if _walk(child):
                    return True
            return False

        # Reset all bold.
        self._unbold_all()

        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if _walk(top):
                break

    # ── selection tracking ──────────────────────────────────────

    def _on_selection_changed(
        self,
        current: QtWidgets.QTreeWidgetItem | None,
        _previous: QtWidgets.QTreeWidgetItem | None,
    ) -> None:
        """Emit the selected session path when a session/fork is picked."""
        self._selected_item = current
        if current is None:
            self.selected_session_changed.emit(None)
            return
        kind = current.data(0, self._ITEM_KIND_ROLE)
        path = current.data(0, self._PATH_ROLE)
        if kind in ("session", "fork") and path:
            self.selected_session_changed.emit(path)
        else:
            self.selected_session_changed.emit(None)

    def execute_action(self, action: str) -> None:
        """Execute *action* on the currently-selected item (same pipeline as context menu)."""
        item = self._selected_item
        if item is None:
            return
        kind = item.data(0, self._ITEM_KIND_ROLE)
        path = item.data(0, self._PATH_ROLE)
        if action == "inspect" and kind in ("session", "fork") and path:
            self.inspect_requested.emit(path)
        elif action == "delete":
            paths = self._collect_descendant_paths(item)
            self._confirm_branch_delete(paths, kind, item)

    # ── context menu ───────────────────────────────────────────

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return

        kind = item.data(0, self._ITEM_KIND_ROLE)
        session_path = item.data(0, self._PATH_ROLE)

        paths_to_delete = self._collect_descendant_paths(item)
        count = len(paths_to_delete)

        is_current = bool(session_path) and session_path == self._current_path
        has_current = bool(self._current_path) and self._current_path in paths_to_delete

        menu = QtWidgets.QMenu(self)

        # ── Switch / Inspect / Rename — only for session/fork ──
        if kind in ("session", "fork"):
            switch_action = menu.addAction("Switch To")
            if is_current:
                switch_action.setEnabled(False)
            menu.addSeparator()
            inspect_action = menu.addAction("Inspect")
            menu.addSeparator()
            rename_action = menu.addAction("Rename")
            menu.addSeparator()

        # ── Delete — for all item types ──
        delete_action = menu.addAction("Delete")
        if is_current or has_current or count == 0:
            delete_action.setEnabled(False)
            if is_current or has_current:
                delete_action.setToolTip("Cannot delete the active session")

        chosen = menu.exec(
            self._tree.viewport().mapToGlobal(pos)
        )
        if chosen is None:
            return

        if kind in ("session", "fork"):
            if chosen == switch_action:
                self.switch_requested.emit(session_path)
                return
            if chosen == inspect_action:
                self.inspect_requested.emit(session_path)
                return
            if chosen == rename_action:
                self._prompt_rename(session_path)
                return

        if chosen == delete_action:
            self._confirm_branch_delete(paths_to_delete, kind, item)

    def _prompt_rename(self, session_path: str) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Session", "New name:"
        )
        if ok and name:
            self.rename_requested.emit(session_path, name)

    # ── branch delete ──────────────────────────────────────────

    def _collect_descendant_paths(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> list[str]:
        """Recursively collect all session file paths under *item*."""
        paths: list[str] = []

        def _walk(it: QtWidgets.QTreeWidgetItem) -> None:
            stored = it.data(0, self._PATH_ROLE)
            if stored and isinstance(stored, str) and stored.endswith(".jsonl"):
                paths.append(stored)
            for i in range(it.childCount()):
                _walk(it.child(i))

        _walk(item)
        return paths

    def _branch_label(self, item: QtWidgets.QTreeWidgetItem, kind: str) -> str:
        """Return a human-readable label for the branch being deleted."""
        if kind == "cwd":
            # Use the formatted label from the item.
            return f"the branch '{item.text(0)}'"
        elif kind == "date":
            return f"the branch '{item.text(0)}'"
        elif kind == "session":
            n_forks = item.childCount()
            if n_forks:
                return f"this session and {n_forks} fork(s)"
            return "this session"
        else:
            return "this fork"

    def _confirm_branch_delete(
        self,
        paths: list[str],
        kind: str,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Confirm and emit deletion of an entire branch."""
        count = len(paths)
        if count == 0:
            return

        label = self._branch_label(item, kind)
        msg = (
            f"Delete {label}?\n\n"
            f"This will permanently remove {count} session file(s)."
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Branch",
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(paths)

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _highlight_item(item: QtWidgets.QTreeWidgetItem) -> None:
        fnt = item.font(0)
        fnt.setBold(True)
        item.setFont(0, fnt)

    def _ensure_visible(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Expand every ancestor so *item* is visible."""
        parent = item.parent()
        while parent is not None:
            self._tree.expandItem(parent)
            parent = parent.parent()

    def _unbold_all(self) -> None:
        """Remove bold from every item in the tree."""

        def _unbold(item: QtWidgets.QTreeWidgetItem) -> None:
            fnt = item.font(0)
            fnt.setBold(False)
            item.setFont(0, fnt)
            for i in range(item.childCount()):
                _unbold(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _unbold(self._tree.topLevelItem(i))

    @staticmethod
    def _parse_session_info(path: Path) -> dict | None:
        """Return session metadata as a dict, or ``None`` on failure.

        Keys returned:
            path             – absolute path (str)
            cwd              – working directory (str)
            timestamp        – ISO timestamp (str)
            parent_session   – absolute parent path (str), or absent
            first_message    – first user message text (str)
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                header_raw = f.readline()

            hdr = json.loads(header_raw)
            if not isinstance(hdr, dict):
                return None

            ts = hdr.get("timestamp") or ""
            ts = str(ts) if ts else ""
            cwd = hdr.get("cwd") or ""
            cwd = str(cwd) if cwd else ""
            parent = hdr.get("parentSession")
            parent = str(parent) if parent else None

            # Fallbacks when header is sparse.
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            ts = ""
            cwd = ""
            parent = None

        if not ts:
            # Filename: <iso>_<uuid>.jsonl
            stem = path.stem
            if "_" in stem:
                ts = stem.split("_", 1)[0]

        if not cwd:
            # Infer from the parent directory name  --home-evert-foo-- → /home/evert/foo
            parent_dir = path.parent.name
            raw = parent_dir.strip("-").replace("-", "/")
            if raw.startswith("/"):
                cwd = raw
            else:
                cwd = ""

        # ── first real user message ───────────────────────────
        first_message = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {}) if isinstance(entry, dict) else None
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    # content can be str or list[dict]
                    if isinstance(content, str):
                        first_message = content
                    elif isinstance(content, list):
                        parts = [
                            b["text"]
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        first_message = " ".join(parts)

                    # Skip MemPalace wake-up prefix.
                    wake_up = "[MemPalace Wake-Up Context"
                    if first_message.startswith(wake_up):
                        # Try to find the real message after the block.
                        idx = first_message.find("\n\n")
                        if idx != -1:
                            after = first_message[idx + 2 :].strip()
                            # If it looks like it still starts with text, use it.
                            if after and not after.startswith("="):
                                first_message = after
                            else:
                                first_message = first_message[:80]
                        else:
                            first_message = first_message[:80]
                    break  # stop at first user message
        except (OSError, UnicodeDecodeError):
            pass

        if not first_message:
            first_message = str(path.stem)

        result: dict = {
            "path": str(path),
            "cwd": cwd or "?",
            "timestamp": ts or "?",
            "first_message": str(first_message),
        }
        if parent:
            result["parent_session"] = parent
        return result

    @staticmethod
    def _find_agent_name_for_fork(
        fork_path: str, parent_path: str
    ) -> str:
        """Open the parent session and return the subagent name that created
        the fork, by matching the fork's creation timestamp against
        ``subagent`` tool-call timestamps in the parent.

        Returns ``"fork"`` if no match is found.
        """
        try:
            fp = Path(fork_path)
            # Get fork creation timestamp from filename:  <iso>_<uuid>.jsonl
            fork_ts = ""
            stem = fp.stem
            if "_" in stem:
                fork_ts = stem.split("_", 1)[0]
            if fork_ts:
                try:
                    ft = float(
                        fork_ts.replace("T", " ").replace("-", ":", 2)
                    )
                except (ValueError, TypeError):
                    fork_ts = ""

            best_match: str = "fork"
            best_diff: float = float("inf")

            pp = Path(parent_path)
            if not pp.exists():
                return "fork"

            with open(pp, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {}) if isinstance(entry, dict) else None
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("role") != "assistant":
                        continue
                    content = msg.get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "toolCall"
                            and block.get("name") == "subagent"
                        ):
                            agent = (
                                block.get("arguments", {})
                                .get("agent", "?")
                                or "?"
                            )
                            if agent == "?":
                                continue  # skip unlabeled
                            # Compare timestamps.
                            tool_entry_ts = entry.get("timestamp", "")
                            if fork_ts and tool_entry_ts:
                                try:
                                    tt = float(
                                        str(tool_entry_ts)
                                        .replace("T", " ")
                                        .replace("-", ":", 2)
                                    )
                                    diff = abs(tt - ft)
                                    if diff < best_diff:
                                        best_diff = diff
                                        best_match = str(agent)
                                except (ValueError, TypeError):
                                    if best_match == "fork":
                                        best_match = str(agent)
                            else:
                                if best_match == "fork":
                                    best_match = str(agent)
            return best_match
        except (OSError, UnicodeDecodeError):
            return "fork"

    @staticmethod
    def _format_cwd_label(cwd_path: str) -> str:
        """Return a short display label for a working directory path."""
        try:
            p = Path(cwd_path).resolve()
            home = Path.home().resolve()
            if str(p).startswith(str(home)):
                rel = str(p)[len(str(home)) :]
                return f"~{rel}" if rel else "~"
        except (OSError, ValueError):
            pass
        return cwd_path

    @staticmethod
    def _format_date_label(date_str: str, count: int) -> str:
        """Return e.g. ``"2026-06-23 (5)"``."""
        return f"{date_str} ({count})"


class WorldSummaryWidget(QtWidgets.QFrame):
    """
    Small read-only world summary panel for the UI.

    Displays only:
      - Project
      - Goals (as bullets)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("World View")
        f = title.font()
        f.setBold(True)
        title.setFont(f)

        self.project_label = QtWidgets.QLabel("Project: (loading…)")

        self.goals_label = QtWidgets.QLabel("Goals:\n(loading…)")  # plain text + wrap
        self.goals_label.setTextFormat(QtCore.Qt.PlainText)
        self.goals_label.setWordWrap(True)

        layout.addWidget(title, 0)
        layout.addWidget(self.project_label, 0)
        layout.addWidget(self.goals_label, 0)
        layout.addStretch(1)

    def refresh_from_world(self, obj: dict) -> None:
        try:
            if not isinstance(obj, dict):
                raise ValueError("world is not a dict")

            project = obj.get("project") or ""
            goals = obj.get("goals") or []
            if not isinstance(goals, list):
                goals = []

            self.project_label.setText(f"Project: {project or '(none)'}")

            if goals:
                goals_text = "\n".join(f"- {g}" for g in goals)
            else:
                goals_text = "(none)"
            self.goals_label.setText(f"Goals:\n{goals_text}")
        except Exception as e:
            self.project_label.setText("Project: (unavailable)")
            self.goals_label.setText(f"Goals:\n(unavailable: {e})")


class MCPServerRowWidget(QtWidgets.QFrame):
    clicked = QtCore.Signal(str)

    def __init__(self, *, server_id: str, parent=None):
        super().__init__(parent)
        self._server_id = server_id
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.label_label = QtWidgets.QLabel("")
        label_font = self.label_label.font()
        label_font.setBold(True)
        self.label_label.setFont(label_font)

        self.enabled_label = QtWidgets.QLabel("")
        self.available_label = QtWidgets.QLabel("")
        self.tools_label = QtWidgets.QLabel("")

        layout.addWidget(self.label_label, 1)
        layout.addWidget(self.enabled_label, 0)
        layout.addWidget(self.available_label, 0)
        layout.addWidget(self.tools_label, 0)

    def set_server_state(
        self,
        *,
        label: str,
        enabled: bool,
        available: bool | None,
        tool_count: int | None,
    ) -> None:
        self.label_label.setText(label)
        self.enabled_label.setText("enabled" if enabled else "disabled")
        self.available_label.setText(self._availability_text(available))
        if tool_count is None:
            self.tools_label.setText("")
        else:
            noun = "tool" if tool_count == 1 else "tools"
            self.tools_label.setText(f"{tool_count} {noun}")

        enabled_bg = "#1f3a2a" if enabled else "#3a2a2a"
        available_bg = "#183b4a" if available else "#4a3520" if available is False else "#333333"
        self.enabled_label.setStyleSheet(
            f"padding: 2px 6px; border-radius: 8px; background: {enabled_bg}; color: white;"
        )
        self.available_label.setStyleSheet(
            f"padding: 2px 6px; border-radius: 8px; background: {available_bg}; color: white;"
        )
        self.tools_label.setStyleSheet("color: #666666;")

    def _availability_text(self, available: bool | None) -> str:
        if available is True:
            return "available"
        if available is False:
            return "unavailable"
        return "unknown"

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self._server_id)
        super().mousePressEvent(event)


class MCPServersPanel(QtWidgets.QFrame):
    serverClicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("MCP servers")
        f = title.font()
        f.setBold(True)
        title.setFont(f)

        self._rows_layout = QtWidgets.QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)

        self._empty_label = QtWidgets.QLabel("No MCP servers configured.")
        self._empty_label.setWordWrap(True)

        layout.addWidget(title, 0)
        layout.addLayout(self._rows_layout, 1)
        layout.addWidget(self._empty_label, 0)

        self._rows: list[MCPServerRowWidget] = []

    def set_servers(self, mcp_config: dict) -> None:
        while self._rows:
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.deleteLater()

        servers = mcp_config.get("servers", {}) if isinstance(mcp_config, dict) else {}
        if not isinstance(servers, dict) or not servers:
            self._empty_label.show()
            return

        self._empty_label.hide()
        for server_id in sorted(servers.keys()):
            server_cfg = servers.get(server_id)
            if not isinstance(server_cfg, dict):
                continue

            row = MCPServerRowWidget(server_id=server_id, parent=self)
            row.clicked.connect(self.serverClicked)

            tools = server_cfg.get("tools", {}) or {}
            available_tools = None
            if isinstance(tools, dict):
                available_tools = sum(
                    1
                    for tool_cfg in tools.values()
                    if isinstance(tool_cfg, dict) and bool(tool_cfg.get("available", False))
                )

            status = server_cfg.get("status", {}) or {}
            available = None
            if isinstance(status, dict) and "available" in status:
                available = bool(status.get("available"))

            row.set_server_state(
                label=str(server_cfg.get("label") or server_id),
                enabled=bool(server_cfg.get("enabled", False)),
                available=available,
                tool_count=available_tools,
            )
            self._rows.append(row)
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch(1)

    def refresh_from_path(self, path: Path) -> None:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                raise ValueError("world_state.json did not contain a JSON object")

            project = obj.get("project") or ""
            goals = obj.get("goals") or []
            if not isinstance(goals, list):
                goals = []

            self.project_label.setText(f"Project: {project or '(none)'}")

            if goals:
                goals_text = "\n".join(f"- {g}" for g in goals)
            else:
                goals_text = "(none)"
            self.goals_label.setText(f"Goals:\n{goals_text}")

        except Exception as e:
            self.project_label.setText("Project: (unavailable)")
            self.goals_label.setText(f"Goals:\n(unavailable: {e})")


class ThalamusLogWindow(QtWidgets.QWidget):
    """
    Separate, modeless window for the Thalamus log.
    """

    def __init__(self, parent: QtWidgets.QWidget | None, session_id: str):
        super().__init__(parent, QtCore.Qt.Window)
        self.session_id = session_id

        self.setWindowTitle("Thalamus Log")
        self.resize(700, 500)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.text_edit = QtWidgets.QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.text_edit.setFont(mono_font)

        save_button = QtWidgets.QPushButton("Save Thalamus Log…", self)
        save_button.clicked.connect(self.save_log)

        layout.addWidget(self.text_edit, 1)
        layout.addWidget(save_button, 0, QtCore.Qt.AlignRight)

    def append_line(self, text: str) -> None:
        self.text_edit.appendPlainText(text)
        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_log(self) -> None:
        default_name = f"thalamus-manual-{self.session_id}.log"

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Thalamus Log",
            default_name,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.text_edit.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Failed to save log:\n{e}"
            )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()


class ThoughtLogWindow(QtWidgets.QWidget):
    """
    Model-provided 'thinking' output (when available).
    """
    def __init__(self, parent: QtWidgets.QWidget | None, session_id: str):
        super().__init__(parent, QtCore.Qt.Window)
        self.session_id = session_id

        self.setWindowTitle("Model Thinking")
        self.resize(700, 500)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.text_edit = QtWidgets.QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.text_edit.setFont(mono_font)

        save_button = QtWidgets.QPushButton("Save Thinking Log…", self)
        save_button.clicked.connect(self.save_log)

        layout.addWidget(self.text_edit, 1)
        layout.addWidget(save_button, 0, QtCore.Qt.AlignRight)

    def append_text(self, text: str) -> None:
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)

        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear(self) -> None:
        self.text_edit.clear()

    def save_log(self) -> None:
        default_name = f"thinking-manual-{self.session_id}.log"

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Thinking Log",
            default_name,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.text_edit.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save log:\n{e}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()


class CombinedLogsWindow(QtWidgets.QWidget):
    """
    Modeless debugging window with four tabs:
      - Thalamus Log
      - Model Thinking
      - World State (full JSON)
      - State (debug view JSON)
    """

    def __init__(self, parent: QtWidgets.QWidget | None, session_id: str):
        super().__init__(parent, QtCore.Qt.Window)
        self.session_id = session_id

        self.setWindowTitle("Debug")
        self.resize(1200, 700)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget(self)
        root.addWidget(self.tabs, 1)

        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)

        # --- Thalamus tab ---
        thalamus_tab = QtWidgets.QWidget(self)
        th_layout = QtWidgets.QVBoxLayout(thalamus_tab)
        th_layout.setContentsMargins(6, 6, 6, 6)
        th_layout.setSpacing(6)

        self.thalamus_edit = QtWidgets.QPlainTextEdit(thalamus_tab)
        self.thalamus_edit.setReadOnly(True)
        self.thalamus_edit.setFont(mono_font)

        save_thalamus = QtWidgets.QPushButton("Save Thalamus Log…", thalamus_tab)
        save_thalamus.clicked.connect(self.save_thalamus_log)

        th_layout.addWidget(self.thalamus_edit, 1)
        th_layout.addWidget(save_thalamus, 0, QtCore.Qt.AlignRight)
        self.tabs.addTab(thalamus_tab, "Thalamus Log")

        # --- Thinking tab ---
        thinking_tab = QtWidgets.QWidget(self)
        tk_layout = QtWidgets.QVBoxLayout(thinking_tab)
        tk_layout.setContentsMargins(6, 6, 6, 6)
        tk_layout.setSpacing(6)

        self.thinking_edit = QtWidgets.QPlainTextEdit(thinking_tab)
        self.thinking_edit.setReadOnly(True)
        self.thinking_edit.setFont(mono_font)

        save_thinking = QtWidgets.QPushButton("Save Thinking Log…", thinking_tab)
        save_thinking.clicked.connect(self.save_thinking_log)

        tk_layout.addWidget(self.thinking_edit, 1)
        tk_layout.addWidget(save_thinking, 0, QtCore.Qt.AlignRight)
        self.tabs.addTab(thinking_tab, "Model Thinking")

        # --- Prompts tab ---
        prompts_tab = QtWidgets.QWidget(self)
        p_layout = QtWidgets.QVBoxLayout(prompts_tab)
        p_layout.setContentsMargins(6, 6, 6, 6)
        p_layout.setSpacing(6)

        self.prompts_edit = QtWidgets.QPlainTextEdit(prompts_tab)
        self.prompts_edit.setReadOnly(True)
        self.prompts_edit.setFont(mono_font)

        save_prompts = QtWidgets.QPushButton("Save Prompts…", prompts_tab)
        save_prompts.clicked.connect(self.save_prompts_log)

        p_layout.addWidget(self.prompts_edit, 1)
        p_layout.addWidget(save_prompts, 0, QtCore.Qt.AlignRight)
        self.tabs.addTab(prompts_tab, "Prompts")

        # --- World tab ---
        world_tab = QtWidgets.QWidget(self)
        w_layout = QtWidgets.QVBoxLayout(world_tab)
        w_layout.setContentsMargins(6, 6, 6, 6)
        w_layout.setSpacing(6)

        self.world_edit = QtWidgets.QPlainTextEdit(world_tab)
        self.world_edit.setReadOnly(True)
        self.world_edit.setFont(mono_font)
        w_layout.addWidget(self.world_edit, 1)
        self.tabs.addTab(world_tab, "World State")

        # --- State tab ---
        state_tab = QtWidgets.QWidget(self)
        s_layout = QtWidgets.QVBoxLayout(state_tab)
        s_layout.setContentsMargins(6, 6, 6, 6)
        s_layout.setSpacing(6)

        self.state_edit = QtWidgets.QPlainTextEdit(state_tab)
        self.state_edit.setReadOnly(True)
        self.state_edit.setFont(mono_font)
        s_layout.addWidget(self.state_edit, 1)
        self.tabs.addTab(state_tab, "State")

    # --- thalamus pane ---

    def append_thalamus_line(self, text: str) -> None:
        self.thalamus_edit.appendPlainText(text)
        sb = self.thalamus_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_thalamus_text(self, text: str) -> None:
        self.thalamus_edit.setPlainText(text)
        sb = self.thalamus_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_thalamus_log(self) -> None:
        default_name = f"thalamus-manual-{self.session_id}.log"
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Thalamus Log",
            default_name,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.thalamus_edit.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save log:\n{e}")

    # --- thinking pane ---

    def append_thinking_text(self, text: str) -> None:
        cursor = self.thinking_edit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.thinking_edit.setTextCursor(cursor)

        sb = self.thinking_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_thinking_text(self, text: str) -> None:
        self.thinking_edit.setPlainText(text)
        sb = self.thinking_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_thinking_log(self) -> None:
        default_name = f"thinking-manual-{self.session_id}.log"
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Thinking Log",
            default_name,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.thinking_edit.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save log:\n{e}")


    # --- prompts pane ---

    def append_prompts_text(self, text: str) -> None:
        cursor = self.prompts_edit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.prompts_edit.setTextCursor(cursor)

        sb = self.prompts_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_prompts_text(self, text: str) -> None:
        self.prompts_edit.setPlainText(text)
        sb = self.prompts_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_prompts_log(self) -> None:
        default_name = f"prompts-manual-{self.session_id}.log"
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Prompts",
            default_name,
            "Log files (*.log);;All files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.prompts_edit.toPlainText())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save log:\n{e}")
    # --- world/state panes ---

    def set_world_json(self, obj) -> None:
        try:
            text = json.dumps(obj if isinstance(obj, dict) else {}, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception as e:
            text = f"<unable to render world: {e}>"
        self.world_edit.setPlainText(text)
        sb = self.world_edit.verticalScrollBar()
        sb.setValue(0)

    def set_state_json(self, obj) -> None:
        try:
            text = json.dumps(obj if isinstance(obj, dict) else {}, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception as e:
            text = f"<unable to render state: {e}>"
        self.state_edit.setPlainText(text)
        sb = self.state_edit.verticalScrollBar()
        sb.setValue(0)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()
