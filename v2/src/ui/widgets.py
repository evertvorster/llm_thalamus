from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class BrainWidget(QtWidgets.QLabel):
    """
    Brain display widget with three states:
      - 'inactive'  -> everything dark
      - 'thalamus'  -> only brainstem/thalamus lit
      - 'llm'       -> whole brain lit

    Transitions between states are cross-faded over ~1 second.
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

        # Load pixmaps for each named state
        self._pixmaps: dict[str, QtGui.QPixmap] = {
            "inactive": self._load_pixmap("inactive.jpg"),
            "thalamus": self._load_pixmap("thalamus.jpg"),
            "llm": self._load_pixmap("llm.jpg"),
        }

        # Current logical state
        self._state: str = "inactive"

        # Animation state
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
        if pm.isNull():
            # Keep silent; the widget will just show black if missing
            return QtGui.QPixmap()
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
        # Hide instead of destroying when the user closes the window.
        event.ignore()
        self.hide()
