"""Tests for the session tree in src/ui/widgets.py — CWD group ordering.

Requires QT_QPA_PLATFORM=offscreen (set in pytest.ini).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _add_session(sessions: Path, dir_name: str, cwd: Path, mtime: float) -> None:
    """Write one session file for *cwd* under a ``--name--/`` directory."""
    group = sessions / f"--{dir_name}--"
    group.mkdir(parents=True)
    f = group / "2026-01-01T00-00-00-000Z_00000000-0000-0000-0000-000000000000.jsonl"
    f.write_text(json.dumps({"cwd": str(cwd)}) + "\n", encoding="utf-8")
    os.utime(f, (mtime, mtime))


def test_cwd_groups_ordered_by_most_recent_use(qapp, tmp_path):
    """A cwd used today outranks one whose sessions are older."""
    from ui.widgets import SessionListWidget

    sessions = tmp_path / "sessions"
    old, recent = tmp_path / "old-project", tmp_path / "recent-project"
    old.mkdir()
    recent.mkdir()
    _add_session(sessions, "old-project", old, 1_000_000)
    _add_session(sessions, "recent-project", recent, 2_000_000)

    tree = SessionListWidget()
    tree.set_sessions(str(sessions), None)

    labels = [
        tree._tree.topLevelItem(i).text(0)
        for i in range(tree._tree.topLevelItemCount())
    ]
    assert labels == [str(recent), str(old)], labels


def test_resumed_session_moves_its_cwd_up(qapp, tmp_path):
    """Recency follows the mtime, not the creation time in the filename."""
    from ui.widgets import SessionListWidget

    sessions = tmp_path / "sessions"
    quiet, busy = tmp_path / "quiet-project", tmp_path / "busy-project"
    quiet.mkdir()
    busy.mkdir()
    _add_session(sessions, "quiet-project", quiet, 3_000_000)
    _add_session(sessions, "busy-project", busy, 1_000_000)

    tree = SessionListWidget()
    tree.set_sessions(str(sessions), None)

    first = tree._tree.topLevelItem(0).text(0)
    assert first.endswith("quiet-project"), first
