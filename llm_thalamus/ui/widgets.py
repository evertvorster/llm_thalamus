from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from paths import get_images_dir  # ← single source of truth


# ---------------------------------------------------------------------------
# Small helper widgets
# ---------------------------------------------------------------------------


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("background-color: black;")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

        self._images_dir: Path = get_images_dir()

        # Load pixmaps for each named state
        self._pixmaps: dict[str, QtGui.QPixmap] = {
            "inactive": self._load_pixmap("inactive.jpg"),
            "thalamus": self._load_pixmap("thalamus.jpg"),
            "llm": self._load_pixmap("llm.jpg"),
        }

        # Current logical state
        self._state: str = "inactive"
        # State we are fading *from*
        self._from_state: str | None = None

        # Crossfade progress [0.0 .. 1.0]
        self._transition: float = 1.0
        self._animating: bool = False

        # Animation: drives the 'transition' property
        self._anim = QtCore.QPropertyAnimation(self, b"transition", self)
        self._anim.setDuration(1000)  # ~1 second fade
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    # --- property used by QPropertyAnimation -------------------------------

    def getTransition(self) -> float:
        return self._transition

    def setTransition(self, value: float) -> None:
        self._transition = float(value)
        self.transitionChanged.emit(self._transition)
        self.update()

    transition = QtCore.Property(
        float, fget=getTransition, fset=setTransition, notify=transitionChanged
    )

    # ----------------------------------------------------------------------

    def _load_pixmap(self, name: str) -> QtGui.QPixmap:
        path = self._images_dir / name
        if path.exists():
            return QtGui.QPixmap(str(path))
        return QtGui.QPixmap()

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

    # --- painting & layout -------------------------------------------------

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

    # --- interaction -------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StatusLight(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._status = "disconnected"

        self.indicator = QtWidgets.QLabel()
        self.indicator.setFixedSize(14, 14)

        self.text_label = QtWidgets.QLabel(label)
        font = self.text_label.font()
        font.setPointSize(font.pointSize() - 1)
        self.text_label.setFont(font)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        layout.addWidget(self.indicator, 0, QtCore.Qt.AlignVCenter)
        layout.addWidget(self.text_label, 0, QtCore.Qt.AlignVCenter)

        self.setStatus("disconnected")

    def setStatus(self, status: str):
        self._status = status
        color = "#6c757d"
        if status == "disconnected":
            color = "#6c757d"
        elif status in ("connected", "idle"):
            color = "#198754"
        elif status == "busy":
            color = "#0d6efd"
        elif status == "error":
            color = "#dc3545"
        self.indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;"
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ChatInput(QtWidgets.QTextEdit):
    sendRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        # bump by ~2 points
        font.setPointSize(font.pointSize() + 2)
        self.setFont(font)
        self.setPlaceholderText("Type your message...")

        # Track current font size so Ctrl+wheel can adjust it
        self._font_size = self.font().pointSizeF() or 14.0

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        # Ctrl + mouse wheel = change font size (like terminals do)
        if event.modifiers() & QtCore.Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 1.0  # points per notch

            if delta > 0:
                self._font_size += step
            elif delta < 0:
                self._font_size -= step

            # Clamp to something sensible
            self._font_size = max(8.0, min(self._font_size, 32.0))
            self._apply_font_size()
            # Don't scroll the text when zooming
            return

        # Normal wheel behaviour when Ctrl is not held
        super().wheelEvent(event)

    def _apply_font_size(self) -> None:
        font = self.font()
        font.setPointSizeF(self._font_size)
        self.setFont(font)


class ThalamusLogWindow(QtWidgets.QWidget):
    """
    Separate, modeless window for the Thalamus log.

    This replaces the old dock-based log view so we don't interfere
    with tiling window managers when showing the log.
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
        # NOTE: LOG_DIR lives in llm_thalamus_ui; we keep the file dialog simple
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
        """
        Hide instead of destroying when the user closes the window.
        """
        event.ignore()
        self.hide()
