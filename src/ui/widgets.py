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
        global _base_input_size
        if _base_input_size == 0:
            p = self.font().pointSize()
            _base_input_size = p if p > 0 else 14
        self._apply_zoom()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            global _input_zoom
            delta = event.angleDelta().y()
            _input_zoom = max(0.5, min(3.0, _input_zoom + (0.1 if delta > 0 else -0.1)))
            self._apply_zoom()
            event.accept()
        else:
            super().wheelEvent(event)

    def _apply_zoom(self):
        fs = max(8, int(_base_input_size * _input_zoom))
        f = self.font()
        f.setPointSize(fs)
        self.setFont(f)


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
    Session list panel for the right sidebar.

    Lists sessions from the pi session directory.  Current session is
    highlighted in bold.  Right-click on a session shows a context menu
    with:
      - Switch To
      - Rename
      - Fork (from current session, using this session as source)
      - Clone (duplicate current branch)
      - Delete

    Signals:
        new_session_requested:  The user wants a fresh session.
        switch_requested:       (session_path: str) Load a different session.
        rename_requested:       (session_path: str, new_name: str)
        delete_requested:       (session_path: str)
    """

    new_session_requested = QtCore.Signal()
    switch_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    delete_requested = QtCore.Signal(str)

    def __init__(self, parent=None):
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

        # ── session list ───────────────────────────────────────
        self._list = QtWidgets.QListWidget()
        self._list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list, 1)

        # ── current session path (set from get_state) ──────────
        self._current_path: str | None = None
        # item → session file path mapping
        self._item_paths: dict[int, str] = {}  # row -> path

    # ── public API ─────────────────────────────────────────────

    def set_sessions(self, session_dir: str | None, current_path: str | None) -> None:
        """
        Populate the list from the on-disk session directory.

        Args:
            session_dir:  Path to ``sessions/`` directory (e.g.
                          ``~/.pi/agent/sessions/``).
            current_path: Absolute path to the currently-loaded
                          session JSONL file, or ``None``.
        """
        self._current_path = current_path
        self._list.clear()
        self._item_paths.clear()

        if not session_dir:
            self._list.addItem("(no session dir)")
            return

        sdir = Path(session_dir)
        if not sdir.is_dir():
            self._list.addItem("(session dir not found)")
            return

        # Collect all .jsonl files from all project subdirectories.
        files: list[tuple[str, Path]] = []  # (iso_timestamp, path)
        for project_dir in sorted(sdir.iterdir()):
            if not project_dir.is_dir():
                continue
            for f in sorted(project_dir.iterdir()):
                if f.suffix != ".jsonl":
                    continue
                # Parse the header line for timestamp and name.
                ts, name = self._parse_session_header(f)
                files.append((ts or f.stem, f))

        # Sort newest-first.
        files.sort(key=lambda x: x[0], reverse=True)

        if not files:
            self._list.addItem("(no sessions)")
            return

        for row, (ts, path) in enumerate(files):
            display = self._format_session_item(path, name_cache={})
            item = QtWidgets.QListWidgetItem(display)
            self._list.addItem(item)
            self._item_paths[row] = str(path)

            if current_path and str(path) == current_path:
                self._highlight_current(item)

    def set_current_session(self, session_path: str | None) -> None:
        """Update which session is highlighted as current."""
        self._current_path = session_path
        for row in range(self._list.count()):
            item = self._list.item(row)
            stored = self._item_paths.get(row)
            if stored == session_path:
                self._highlight_current(item)
            else:
                fnt = item.font()
                fnt.setBold(False)
                item.setFont(fnt)

    # ── context menu ───────────────────────────────────────────

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return

        row = self._list.row(item)
        session_path = self._item_paths.get(row)
        if not session_path:
            return

        is_current = session_path == self._current_path

        menu = QtWidgets.QMenu(self)

        switch_action = menu.addAction("Switch To")

        menu.addSeparator()
        rename_action = menu.addAction("Rename")

        menu.addSeparator()
        fork_action = menu.addAction("Fork")
        clone_action = menu.addAction("Clone")

        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        if is_current:
            delete_action.setEnabled(False)
            delete_action.setToolTip("Cannot delete the active session")

        # Disable switch if it's already the current session.
        if is_current:
            switch_action.setEnabled(False)

        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if chosen == switch_action:
            self.switch_requested.emit(session_path)
        elif chosen == rename_action:
            self._prompt_rename(session_path)
        elif chosen == fork_action:
            # Forking from a different session makes more sense
            # as "switch + fork from last user message", so we
            # just switch for now.
            self.switch_requested.emit(session_path)
        elif chosen == clone_action:
            # Clone duplicates the current branch in a new session.
            # The user likely wants to switch first, then clone.
            self.switch_requested.emit(session_path)
        elif chosen == delete_action:
            self._confirm_delete(session_path)

    def _prompt_rename(self, session_path: str) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Session",
            "New name:",
        )
        if ok and name:
            self.rename_requested.emit(session_path, name)

    def _confirm_delete(self, session_path: str) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Session",
            f"Delete this session?\n\n{session_path}",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(session_path)

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _highlight_current(item: QtWidgets.QListWidgetItem) -> None:
        fnt = item.font()
        fnt.setBold(True)
        item.setFont(fnt)

    @staticmethod
    def _parse_session_header(path: Path) -> tuple[str | None, str | None]:
        """Return (iso_timestamp, display_name) from the session file header.

        Reads only the first line of the JSONL file.
        """
        ts: str | None = None
        name: str | None = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                first = f.readline().strip()
                if first:
                    hdr = json.loads(first)
                    if isinstance(hdr, dict):
                        ts = hdr.get("timestamp") or None
                        if ts:
                            ts = str(ts)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Fallback: use the filename timestamp portion.
        if not ts:
            # filename: <iso>_<uuid>.jsonl
            stem = path.stem
            if "_" in stem:
                ts = stem.split("_", 1)[0]

        return ts, name

    @staticmethod
    def _format_session_item(
        path: Path,
        name_cache: dict,
    ) -> str:
        """Build a one-line display string for a session."""
        ts, name = SessionListWidget._parse_session_header(path)

        # Date portion.
        date_str = "?"
        if ts:
            # Try ISO format: 2026-06-22T07-17-33-920Z
            # Also handle plain "2026-06-22"
            cleaned = ts.replace("T", " ").replace("-", ":", 2) if "T" in ts else ts
            if len(cleaned) >= 10:
                date_str = cleaned[:10]

        label = name or path.stem
        return f"{date_str}  {label[:60]}"


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
