"""Tests for the chat input's file paths in src/ui/widgets.py."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Bar:
    """Stands in for AttachmentBar: a widget that records what was added."""

    @staticmethod
    def make(parent=None):
        from PySide6.QtWidgets import QWidget

        class _BarWidget(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.added: list[str] = []

            def add_dropped_file(self, path: str) -> None:
                self.added.append(path)

        return _BarWidget(parent)


def _input_with_bar(qapp):
    """A ChatInput whose parent chain contains something like AttachmentBar.

    The chain of parents is returned with it: Qt widgets are owned by their
    parent, so letting a parent here go out of scope deletes the input too.
    """
    from PySide6.QtWidgets import QWidget

    from ui.widgets import ChatInput

    holder = QWidget()
    bar = _Bar.make(holder)
    child = QWidget(bar)
    chat_input = ChatInput(child)
    return chat_input, bar, (holder, child)


def _image_mime():
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QColor, QImage

    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    mime = QMimeData()
    mime.setImageData(image)
    return mime


class TestPastedImages:
    def test_two_pastes_in_one_second_do_not_overwrite(self, qapp, tmp_path, monkeypatch):
        """The name used to carry only a second-resolution timestamp."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        chat_input, bar, _parents = _input_with_bar(qapp)

        chat_input.insertFromMimeData(_image_mime())
        chat_input.insertFromMimeData(_image_mime())

        assert len(bar.added) == 2
        assert bar.added[0] != bar.added[1]
        assert all(Path(p).exists() for p in bar.added)

    def test_nothing_is_written_without_an_attachment_bar(self, qapp, tmp_path, monkeypatch):
        """A paste into a bare ChatInput must not leave an orphan file."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        from ui.widgets import ChatInput

        chat_input = ChatInput()

        chat_input.insertFromMimeData(_image_mime())

        attach_dir = tmp_path / ".pi" / "agent" / "sessions" / "attachments"
        assert not attach_dir.exists() or not any(attach_dir.iterdir())
