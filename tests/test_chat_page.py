"""Tests for the page's URL bridge and its navigation policy.

``_ChatPage`` is the only path from rendered HTML back into Python, and the only
place where a link click is decided.  Both are worth pinning: a click that the
view handles itself replaces the transcript with the page.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    from ui.chat_renderer import _ChatPage

    return _ChatPage()


def _click(url: str, page):
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage

    return page.acceptNavigationRequest(
        QUrl(url), QWebEnginePage.NavigationTypeLinkClicked, True
    )


class TestNavigationPolicy:
    def test_http_link_goes_to_the_desktop(self, page, monkeypatch):
        from ui import chat_renderer

        opened: list[str] = []
        monkeypatch.setattr(
            chat_renderer.QDesktopServices,
            "openUrl",
            lambda url: opened.append(url.toString()),
        )

        allowed = _click("https://example.com/docs", page)

        assert allowed is False                     # the view does not navigate
        assert opened == ["https://example.com/docs"]

    def test_file_link_goes_to_the_desktop(self, page, monkeypatch):
        from ui import chat_renderer

        opened: list[str] = []
        monkeypatch.setattr(
            chat_renderer.QDesktopServices,
            "openUrl",
            lambda url: opened.append(url.toString()),
        )

        assert _click("file:///tmp/notes.txt", page) is False
        assert opened == ["file:///tmp/notes.txt"]

    def test_initial_load_is_not_a_link_click(self, page):
        """setHtml's own load must be allowed, or nothing would ever render."""
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage

        allowed = page.acceptNavigationRequest(
            QUrl("about:blank"), QWebEnginePage.NavigationTypeOther, True
        )
        assert allowed is True


class TestThalamusUrls:
    def test_copy_request_is_emitted_and_never_navigated(self, qtbot, page):
        # qtbot rather than connect-and-hope: waitSignal fails the test when the
        # signal never arrives, instead of asserting on an empty list.
        with qtbot.waitSignal(page.copyRequested, timeout=1000) as blocker:
            allowed = _click("thalamus://copy/hello%20world", page)

        assert allowed is False
        assert blocker.args == ["hello world"]

    def test_page_navigation_request(self, page):
        target: list[int] = []
        page.navigatePageRequested.connect(target.append)

        assert _click("thalamus://navigate-page/2", page) is False
        assert target == [2]

    def test_a_bad_page_number_is_ignored(self, page):
        target: list[int] = []
        page.navigatePageRequested.connect(target.append)

        assert _click("thalamus://navigate-page/not-a-number", page) is False
        assert target == []
