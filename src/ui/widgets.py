from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .theme import THINKING_COLORS


def _attachment_bar(widget: QtWidgets.QWidget | None):
    """The AttachmentBar above *widget* in the parent chain, or None.

    Duck-typed rather than imported: attachment_bar imports this module for
    ChatInput, so naming its class here would be a cycle.
    """
    parent = widget
    while parent is not None:
        if hasattr(parent, "add_dropped_file"):
            return parent
        parent = parent.parent()
    return None


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
        # QPlainTextEdit defaults to NoWrap, so long prompts scrolled sideways
        # instead of wrapping.  Wrapping is also what lets the input grow a
        # line at a time as text is typed.
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
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
            bar = _attachment_bar(self.parent())
            if not img.isNull() and bar is not None:
                attach_dir = Path.home() / ".pi" / "agent" / "sessions" / "attachments"
                attach_dir.mkdir(parents=True, exist_ok=True)
                ts = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd_hh-mm-ss")
                # mkstemp, not a timestamped name: two pastes in the same second
                # would otherwise write the same path and the first image vanish.
                fd, out_path = tempfile.mkstemp(
                    prefix=f"pasted-image-{ts}-", suffix=".png", dir=str(attach_dir)
                )
                os.close(fd)
                if img.save(out_path, "PNG"):
                    bar.add_dropped_file(out_path)
                else:
                    os.unlink(out_path)
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
        bar = _attachment_bar(self.parent())
        if bar is not None:
            for url in urls:
                bar.add_dropped_file(url.toLocalFile())

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
    _CWD_EXISTS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2

    new_session_with_cwd = QtCore.Signal(str)  # cwd path
    switch_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    delete_requested = QtCore.Signal(list)
    inspect_requested = QtCore.Signal(str)
    selected_session_changed = QtCore.Signal(object)  # str | None
    cwd_exists_changed = QtCore.Signal(bool)  # True if selected item's CWD exists

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
        # pi-subagents writes run transcripts here; they are not sessions and
        # pi refuses to open them.
        if "subagent-artifacts" in parts[1:]:
            return None

        # cwd from parent directory name  --home-evert-foo-- → /home/evert/foo
        raw = parts[0].strip("-").replace("-", "/")
        cwd = f"/{raw}" if raw else "?"

        # timestamp from filename
        ts = path.stem.split("_", 1)[0] if "_" in path.stem else "?"

        # When the session was last used — the filename keeps its creation
        # time, so only the mtime moves when an old session is resumed.
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0

        result: dict = {
            "path": str(path),
            "cwd": cwd,
            "timestamp": ts,
            "mtime": mtime,
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

        # ── 2. resolve real CWD paths from session file headers ──
        # The inferred CWD (decoded from directory name) is lossy for
        # directories containing hyphens.  Read one session file per
        # CWD group to get the true path from the JSONL header.
        real_cwd: dict[str, tuple[str, bool]] = {}  # inferred → (real_path, exists)
        for inferred, infos in cwd_sessions.items():
            for info in infos:
                try:
                    with open(info["path"], "r", encoding="utf-8") as f:
                        first = f.readline()
                    if first:
                        header = json.loads(first)
                        actual = header.get("cwd")
                        if actual:
                            rp = str(actual)
                            real_cwd[inferred] = (rp, os.path.isdir(rp))
                            break
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
            # If no session file could be read, keep the inferred path.
            if inferred not in real_cwd:
                real_cwd[inferred] = (inferred, os.path.isdir(inferred))

        # ── 3. sort CWD keys: current first, then most recently used ──
        cwd_now = str(Path.cwd())
        cwd_keys = sorted(
            cwd_sessions,
            key=lambda c: (
                c != cwd_now,
                -max(i["mtime"] for i in cwd_sessions[c]),
                c,
            ),
        )

        dead_color = QtGui.QColor("#999999")

        for inferred_key in cwd_keys:
            real_path, exists = real_cwd.get(inferred_key, (inferred_key, True))
            cwd_item = QtWidgets.QTreeWidgetItem(
                [self._format_cwd_label(real_path)]
            )
            cwd_item.setData(0, self._ITEM_KIND_ROLE, "cwd")
            cwd_item.setData(0, self._PATH_ROLE, real_path)
            cwd_item.setData(0, self._CWD_EXISTS_ROLE, exists)
            if not exists:
                cwd_item.setForeground(0, dead_color)
            self._tree.addTopLevelItem(cwd_item)

            # ── group by date ──────────────────────────────────
            infos = cwd_sessions[inferred_key]

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

            # Grey out all children if the CWD directory is gone.
            if not exists:
                self._grey_out_branch(cwd_item, dead_color)

            if inferred_key == cwd_now:
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
            self.cwd_exists_changed.emit(True)  # default when nothing selected
            self.selected_session_changed.emit(None)
            return
        kind = current.data(0, self._ITEM_KIND_ROLE)
        path = current.data(0, self._PATH_ROLE)
        # Emit CWD existence for any selected item.
        self.cwd_exists_changed.emit(self._get_cwd_exists(current))
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
    def selected_item_kind(self) -> str | None:
        """Kind of the currently selected tree item: 'cwd', 'date', 'session', 'fork', or None."""
        item = self._tree.currentItem()
        return item.data(0, self._ITEM_KIND_ROLE) if item else None

    @property
    def selected_cwd_exists(self) -> bool:
        """True if the selected item's CWD exists on disk."""
        item = self._tree.currentItem()
        return self._get_cwd_exists(item) if item else True

    @property
    def selected_is_current(self) -> bool:
        """True if the selected item is the current (active) session."""
        item = self._tree.currentItem()
        if item is None:
            return False
        path = item.data(0, self._PATH_ROLE)
        return bool(path) and path == self._current_path

    def execute_action(self, action: str) -> None:
        """Execute *action* on the currently-selected tree item.

        Single dispatch for all selected-item operations — replaces
        the old context menu.
        """
        item = self._tree.currentItem()
        if item is None:
            return
        kind = item.data(0, self._ITEM_KIND_ROLE)
        path = item.data(0, self._PATH_ROLE)
        cwd = self._get_item_cwd(item)
        cwd_exists = self._get_cwd_exists(item) if cwd else False

        if action == "switch" and kind in ("session", "fork") and path:
            if path != self._current_path:
                self.switch_requested.emit(path)

        elif action == "new_session" and cwd and cwd_exists:
            self.new_session_with_cwd.emit(cwd)

        elif action == "inspect" and kind in ("session", "fork") and path:
            self.inspect_requested.emit(path)

        elif action == "rename" and kind in ("session", "fork") and path:
            self._prompt_rename(path)

        elif action == "delete":
            paths = self._collect_descendant_paths(item)
            self._confirm_branch_delete(paths, kind, item)

        elif action == "create_dir" and cwd and not cwd_exists:
            try:
                os.makedirs(cwd, exist_ok=True)
            except OSError as e:
                QtWidgets.QMessageBox.warning(
                    self, "Create Directory",
                    f"Failed to create {cwd}:\n{e}",
                )
                return
            # Update existence flag and re-color the branch.
            cwd_item = item
            if kind != "cwd":
                p = item.parent()
                while p is not None:
                    if p.data(0, self._ITEM_KIND_ROLE) == "cwd":
                        cwd_item = p
                        break
                    p = p.parent()
            if cwd_item.data(0, self._ITEM_KIND_ROLE) == "cwd":
                cwd_item.setData(0, self._CWD_EXISTS_ROLE, True)
                self._reset_branch_foreground(cwd_item)
                self.cwd_exists_changed.emit(True)

    # ── helpers ────────────────────────────────────────────────

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

    @staticmethod
    def _get_cwd_exists(item: QtWidgets.QTreeWidgetItem) -> bool:
        """Walk up the tree to find the CWD item and return its existence flag."""
        kind = item.data(0, SessionListWidget._ITEM_KIND_ROLE)
        if kind == "cwd":
            return bool(item.data(0, SessionListWidget._CWD_EXISTS_ROLE))
        parent = item.parent()
        while parent is not None:
            pk = parent.data(0, SessionListWidget._ITEM_KIND_ROLE)
            if pk == "cwd":
                return bool(parent.data(0, SessionListWidget._CWD_EXISTS_ROLE))
            parent = parent.parent()
        return True

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
    def _grey_out_branch(item: QtWidgets.QTreeWidgetItem, color: QtGui.QColor) -> None:
        """Recursively grey out *item* and all its children."""
        item.setForeground(0, color)
        for i in range(item.childCount()):
            SessionListWidget._grey_out_branch(item.child(i), color)

    @staticmethod
    def _reset_branch_foreground(item: QtWidgets.QTreeWidgetItem) -> None:
        """Recursively clear the foreground color on *item* and its children."""
        item.setForeground(0, QtGui.QBrush())
        for i in range(item.childCount()):
            SessionListWidget._reset_branch_foreground(item.child(i))

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
