from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


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

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)


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
    Modeless window with two panes:
      - Left: Thalamus log
      - Right: Model thinking log
    """

    def __init__(self, parent: QtWidgets.QWidget | None, session_id: str):
        super().__init__(parent, QtCore.Qt.Window)
        self.session_id = session_id

        self.setWindowTitle("Logs")
        self.resize(1100, 600)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)

        # --- left: thalamus log ---
        left = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        left_label = QtWidgets.QLabel("Thalamus Log", left)
        self.thalamus_edit = QtWidgets.QPlainTextEdit(left)
        self.thalamus_edit.setReadOnly(True)

        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.thalamus_edit.setFont(mono_font)

        save_thalamus = QtWidgets.QPushButton("Save Thalamus Log…", left)
        save_thalamus.clicked.connect(self.save_thalamus_log)

        left_layout.addWidget(left_label, 0)
        left_layout.addWidget(self.thalamus_edit, 1)
        left_layout.addWidget(save_thalamus, 0, QtCore.Qt.AlignRight)

        # --- right: thinking log ---
        right = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        right_label = QtWidgets.QLabel("Model Thinking", right)
        self.thinking_edit = QtWidgets.QPlainTextEdit(right)
        self.thinking_edit.setReadOnly(True)
        self.thinking_edit.setFont(mono_font)

        save_thinking = QtWidgets.QPushButton("Save Thinking Log…", right)
        save_thinking.clicked.connect(self.save_thinking_log)

        right_layout.addWidget(right_label, 0)
        right_layout.addWidget(self.thinking_edit, 1)
        right_layout.addWidget(save_thinking, 0, QtCore.Qt.AlignRight)

        splitter.addWidget(left)
        splitter.addWidget(right)

        # Make Thalamus log ~20% and Thinking log ~80%
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        root.addWidget(splitter, 1)

        # Seed initial splitter sizes after layout
        QtCore.QTimer.singleShot(
            0,
            lambda: splitter.setSizes([int(self.width() * 0.2),
                                    int(self.width() * 0.8)])
        )


    # --- thalamus pane ---

    def append_thalamus_line(self, text: str) -> None:
        self.thalamus_edit.appendPlainText(text)
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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        event.ignore()
        self.hide()
