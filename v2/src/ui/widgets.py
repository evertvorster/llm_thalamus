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
        self.setPlaceholderText("Type here… (Enter to send, Shift+Enter for newline)")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            # Shift+Enter → newline
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
                return

            # Enter → send
            self.sendRequested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class BrainWidget(QtWidgets.QLabel):
    """
    Brain display widget with three states:
      - 'inactive'  -> everything dark
      - 'thalamus'  -> only brainstem/thalamus lit
      - 'llm'       -> whole brain lit
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

    # --- state handling --------------------------------------------------------

    def _load_pixmap(self, filename: str) -> QtGui.QPixmap:
        path = self._images_dir / filename
        pm = QtGui.QPixmap(str(path))
        return pm

    def set_state(self, state: str) -> None:
        if state not in ("inactive", "thalamus", "llm"):
            state = "inactive"

        if state == self._state and not self._animating:
            return

        if (
            self._state == "inactive"
            and self._from_state is None
            and not self._animating
        ):
            self._state = state
            self._from_state = None
            self._animating = False
            self._anim.stop()
            self.setTransition(1.0)
            return

        self._from_state = self._state
        self._state = state
        self._animating = True

        self._anim.stop()
        self.setTransition(0.0)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        self._animating = False
        self._from_state = None
        self.setTransition(1.0)

    # --- painting & layout -----------------------------------------------------

    def _get_pixmap_for_state(self, state: str | None) -> QtGui.QPixmap | None:
        if not state:
            return None
        pm = self._pixmaps.get(state)
        if pm is None or pm.isNull():
            return None
        return pm

    def _scaled_rect(
        self,
        pm: QtGui.QPixmap,
        target_rect: QtCore.QRect,
    ) -> tuple[QtCore.QRect, QtGui.QPixmap]:
        if pm is None or pm.isNull() or not target_rect.isValid():
            return target_rect, pm

        scaled = pm.scaled(
            target_rect.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        x = target_rect.center().x() - scaled.width() // 2
        y = target_rect.center().y() - scaled.height() // 2
        dest = QtCore.QRect(x, y, scaled.width(), scaled.height())
        return dest, scaled

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.black)

        rect = self.rect()
        if not rect.isValid():
            return

        current_pm = self._get_pixmap_for_state(self._state)

        if (
            not self._animating
            or self._from_state is None
            or not (0.0 <= self._transition <= 1.0)
        ):
            if current_pm is None:
                return
            dest, scaled = self._scaled_rect(current_pm, rect)
            painter.drawPixmap(dest, scaled)
            return

        from_pm = self._get_pixmap_for_state(self._from_state)
        to_pm = current_pm

        if from_pm is not None:
            dest_from, scaled_from = self._scaled_rect(from_pm, rect)
            painter.save()
            painter.setOpacity(1.0 - self._transition)
            painter.drawPixmap(dest_from, scaled_from)
            painter.restore()

        if to_pm is not None:
            dest_to, scaled_to = self._scaled_rect(to_pm, rect)
            painter.save()
            painter.setOpacity(self._transition)
            painter.drawPixmap(dest_to, scaled_to)
            painter.restore()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update()

    # --- interaction ----------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class WorldSummaryWidget(QtWidgets.QFrame):
    """
    Small read-only world summary panel for the UI "Spaces" area.

    Intentionally dumb:
      - Reads world_state.json from a provided Path
      - Displays: Project, Goals
      - No config/path resolution here (callers supply path)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._title = QtWidgets.QLabel("World")
        self._title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)

        self.project_label = QtWidgets.QLabel("Project: (loading…)")

        self.goals_label = QtWidgets.QLabel("Goals:\n(loading…)")
        self.goals_label.setTextFormat(QtCore.Qt.PlainText)
        self.goals_label.setWordWrap(True)

        layout.addWidget(self._title, 0)
        layout.addWidget(self.project_label, 0)
        layout.addWidget(self.goals_label, 0)
        layout.addStretch(1)

    def refresh_from_path(self, world_path: Path) -> None:
        try:
            data = json.loads(Path(world_path).read_text(encoding="utf-8"))
            project = data.get("project") or ""
            goals = data.get("goals") or []
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
        # appendPlainText adds a newline; for deltas we want raw append.
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
