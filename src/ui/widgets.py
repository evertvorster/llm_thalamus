from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .theme import THINKING_COLORS


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

    def set_thinking_border_color(self, level: str) -> None:
        """Set the input border color to indicate thinking level."""
        color = THINKING_COLORS.get(level, "#888888")
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

    Supports a "brightness" factor used by the UI while model thinking is active.
    This is exposed as a real Qt property so we can smoothly animate it.
    """

    clicked = QtCore.Signal()
    transitionChanged = QtCore.Signal(float)

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

        # Brightness factor (1.0 = unchanged). Used for thinking pulse.
        self._brightness: float = 1.0

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

    # --- QProperty: brightness ------------------------------------------------

    def getBrightness(self) -> float:
        return self._brightness

    def setBrightness(self, value: float) -> None:
        v = float(value)
        if v < 0.0:
            v = 0.0
        if v > 1.0:
            v = 1.0
        v = round(v, 3)
        if v == self._brightness:
            return
        self._brightness = v
        self.update()

    brightness = QtCore.Property(
        float, fget=getBrightness, fset=setBrightness
    )

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

        r = self.rect()
        scaled = pm.scaled(
            r.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        x = (r.width() - scaled.width()) // 2
        y = (r.height() - scaled.height()) // 2

        # Use opacity for brightness (black background + dimmer pixels = reduced V).
        if self._brightness < 1.0:
            painter.setOpacity(self._brightness)
        painter.drawPixmap(x, y, scaled)
        if self._brightness < 1.0:
            painter.setOpacity(1.0)


# ── helpers ──────────────────────────────────────────────────────────


def _trim_label(text: str, max_len: int = 55) -> str:
    """Truncate *text* to *max_len* chars, appending \"…\" if truncated.
    Strips newlines and collapses whitespace."""
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


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
    new_session_with_cwd = QtCore.Signal(str)  # cwd path
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
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree, 1)

        self._current_path: str | None = None
        self._selected_item: QtWidgets.QTreeWidgetItem | None = None

    # ── public API ─────────────────────────────────────────────

    @staticmethod
    def _infer_session_info(
        session_dir: Path, path: Path
    ) -> dict | None:
        """Return session metadata from *path* without opening the file.

        All fields are inferred from the filesystem path:

        * ``cwd`` — decoded from the CWD directory name (``--a-b-c--`` → ``/a/b/c``).
        * ``timestamp`` — from the filename stem.
        * ``parent_session`` — set automatically when *path* is a nested
          ``session.jsonl`` inside a ``/run‑N/`` subdirectory.
        """
        try:
            rel = path.relative_to(session_dir)
        except ValueError:
            return None
        parts = rel.parts
        if not parts:
            return None

        # cwd from parent directory name  --home-evert-foo-- → /home/evert/foo
        raw = parts[0].strip("-").replace("-", "/")
        cwd = f"/{raw}" if raw else "?"

        # timestamp from filename
        ts = path.stem.split("_", 1)[0] if "_" in path.stem else "?"

        result: dict = {
            "path": str(path),
            "cwd": cwd,
            "timestamp": ts,
        }

        # fork detection: nested session.jsonl → link to parent
        if path.name == "session.jsonl" and len(parts) >= 4:
            parent_path = session_dir / parts[0] / f"{parts[1]}.jsonl"
            if parent_path.exists():
                result["parent_session"] = str(parent_path)

        return result

    @staticmethod
    def _get_first_message(path: Path) -> str:
        """Read the first user message from *path*. Returns empty string if
        no user message is found."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {})
                    if not isinstance(msg, dict) or msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        msg_text = content
                    elif isinstance(content, list):
                        parts = [
                            b["text"]
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        msg_text = " ".join(parts)
                    else:
                        continue
                    if msg_text and not msg_text.startswith("[MemPalace"):
                        return msg_text[:80]
        except (OSError, UnicodeDecodeError):
            pass
        return path.stem

    @staticmethod
    def _fork_agent_name(fork_path: Path) -> str:
        """Return agent label for a fork. Reads agent name from the
        ``subagent-artifacts/<run_id>_*_meta.json`` file. Falls back to
        the run ID directory name."""
        run_id = fork_path.parent.parent.name
        # Walk up to find subagent-artifacts/ and the matching meta file
        for parent in fork_path.parents:
            artifacts = parent / "subagent-artifacts"
            if artifacts.is_dir():
                prefix = f"{run_id}_"
                for f in artifacts.iterdir():
                    if f.name.startswith(prefix) and f.suffix == ".json":
                        try:
                            data = json.loads(f.read_text(encoding="utf-8"))
                            return data.get("agent", run_id)[:20]
                        except (OSError, json.JSONDecodeError):
                            pass
                break
        return run_id[:16]

    def set_sessions(
        self, session_dir: str | None, current_path: str | None
    ) -> None:
        """Populate the tree from all ``--*--/`` directories under *session_dir*.

        Items are grouped: CWD → date → parent-session → fork.
        Metadata is inferred from filesystem paths; file contents are not
        read during initial population.
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

        # ── 1. discover all sessions ───────────────────────────
        parents: dict[str, dict] = {}  # path → info (sessions w/o parent_session)
        forks: dict[str, list[dict]] = {}  # parent_path → [fork_info]
        cwd_sessions: dict[str, list[dict]] = {}  # cwd → [info, ...]

        for jsonl_path in sorted(sdir.rglob("*.jsonl")):
            info = self._infer_session_info(sdir, jsonl_path)
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

            by_date: dict[str, list[dict]] = {}
            for info in infos:
                ts = info.get("timestamp", "")
                date = ts[:10] if len(ts) >= 10 else "?"
                by_date.setdefault(date, []).append(info)

            for date in sorted(by_date.keys(), reverse=True):
                day = by_date[date]

                # parents (no parent_session)
                day_parents = sorted(
                    (i for i in day if not i.get("parent_session")),
                    key=lambda i: i.get("timestamp", ""),
                    reverse=True,
                )

                # orphan forks (parent not found in *any* date)
                orphan_forks = [
                    i for i in day
                    if i.get("parent_session")
                    and i["parent_session"] not in parents
                ]

                visible = len(day_parents) + len(orphan_forks)
                if visible == 0:
                    continue

                date_item = QtWidgets.QTreeWidgetItem(
                    [self._format_date_label(date, visible)]
                )
                fnt = date_item.font(0)
                fnt.setBold(True)
                date_item.setFont(0, fnt)
                date_item.setData(0, self._ITEM_KIND_ROLE, "date")
                date_item.setData(0, self._PATH_ROLE, date)
                cwd_item.addChild(date_item)

                for pinfo in day_parents:
                    display = Path(pinfo["path"]).stem[:80]
                    p_item = QtWidgets.QTreeWidgetItem([display])
                    p_item.setData(0, self._ITEM_KIND_ROLE, "session")
                    p_item.setData(0, self._PATH_ROLE, pinfo["path"])
                    date_item.addChild(p_item)

                    # forks of this parent
                    p_forks = sorted(
                        forks.get(pinfo["path"], []),
                        key=lambda fi: fi.get("timestamp", ""),
                    )
                    for fi in p_forks:
                        label = self._fork_agent_name(Path(fi["path"]))
                        f_item = QtWidgets.QTreeWidgetItem([label])
                        f_item.setData(0, self._ITEM_KIND_ROLE, "fork")
                        f_item.setData(0, self._PATH_ROLE, fi["path"])
                        p_item.addChild(f_item)

                # orphan forks
                for fi in orphan_forks:
                    label = self._fork_agent_name(Path(fi["path"]))
                    f_item = QtWidgets.QTreeWidgetItem([label])
                    f_item.setData(0, self._ITEM_KIND_ROLE, "fork")
                    f_item.setData(0, self._PATH_ROLE, fi["path"])
                    date_item.addChild(f_item)

            if cwd == cwd_now:
                self._tree.expandItem(cwd_item)

        # ── 3. enrich highlighted item ─────────────────────────
        self.set_current_session(self._current_path)

    def set_current_session(self, session_path: str | None) -> None:
        """Update which session / fork is highlighted and enrich the
        label with the first user message (lazy load)."""
        self._current_path = session_path

        def _walk(item: QtWidgets.QTreeWidgetItem) -> bool:
            for i in range(item.childCount()):
                child = item.child(i)
                stored = child.data(0, self._PATH_ROLE)
                if stored and stored == session_path:
                    self._highlight_item(child)
                    self._ensure_visible(child)
                    if child.data(0, self._ITEM_KIND_ROLE) == "session":
                        msg = self._get_first_message(Path(session_path))
                        if msg and child.text(0) != msg:
                            child.setText(0, msg)
                    return True
                if _walk(child):
                    return True
            return False

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

    def _on_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Lazily enrich session labels with first user message text.
        Only processes direct children — expanding a CWD does not crawl
        into collapsed date groups."""
        for i in range(item.childCount()):
            child = item.child(i)
            kind = child.data(0, self._ITEM_KIND_ROLE)
            path = child.data(0, self._PATH_ROLE)
            if kind != "session" or not path:
                continue
            msg = self._get_first_message(Path(path))
            if msg and child.text(0) != msg:
                child.setText(0, _trim_label(msg, 55))

    @property
    def suggested_cwd(self) -> str | None:
        """Return the CWD of the currently selected tree item, if any."""
        if self._selected_item is not None:
            return self._get_item_cwd(self._selected_item)
        return None

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

    @staticmethod
    def _get_item_cwd(item: QtWidgets.QTreeWidgetItem) -> str | None:
        """Walk up the tree to find the CWD path for *item*.

        For CWD-level items the path is stored directly.  For date,
        session, and fork items we walk up to the first CWD ancestor.
        """
        kind = item.data(0, SessionListWidget._ITEM_KIND_ROLE)
        path = item.data(0, SessionListWidget._PATH_ROLE)
        if kind == "cwd" and isinstance(path, str):
            return path
        parent = item.parent()
        while parent is not None:
            pk = parent.data(0, SessionListWidget._ITEM_KIND_ROLE)
            pp = parent.data(0, SessionListWidget._PATH_ROLE)
            if pk == "cwd" and isinstance(pp, str):
                return pp
            parent = parent.parent()
        return None

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

        # ── New Session — for all item types (CWD already known) ──
        cwd = self._get_item_cwd(item)
        new_action = menu.addAction("New Session")
        if not cwd:
            new_action.setEnabled(False)
            new_action.setToolTip("Could not determine working directory")
        menu.addSeparator()

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

        if chosen == new_action and cwd:
            self.new_session_with_cwd.emit(cwd)
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
