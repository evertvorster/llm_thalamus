from __future__ import annotations

from pathlib import Path

from runtime.tools.bindings import bash as bind_bash
from runtime.tools.bindings import edit as bind_edit
from runtime.tools.bindings import read as bind_read
from runtime.tools.bindings import write as bind_write
from runtime.tools.resources import ToolResources


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        _ = limit
        return []


def _resources(tmp_path: Path) -> ToolResources:
    return ToolResources(chat_history=_StubChatHistory(), working_dir=tmp_path)


def test_read_write_edit_file_tools(tmp_path: Path) -> None:
    resources = _resources(tmp_path)

    write = bind_write.bind(resources)
    read = bind_read.bind(resources)
    edit = bind_edit.bind(resources)

    result = write({"path": "notes/example.txt", "content": "alpha\nbeta\ngamma\n"})
    assert result["ok"] is True
    assert (tmp_path / "notes" / "example.txt").read_text(encoding="utf-8") == "alpha\nbeta\ngamma\n"

    read_result = read({"path": "notes/example.txt", "offset": 2, "limit": 1})
    assert read_result["ok"] is True
    assert read_result["content"] == "beta\n"

    edit_result = edit(
        {
            "path": "notes/example.txt",
            "edits": [{"oldText": "beta", "newText": "BETA"}],
        }
    )
    assert edit_result["ok"] is True
    assert (tmp_path / "notes" / "example.txt").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"


def test_edit_requires_unique_old_text(tmp_path: Path) -> None:
    resources = _resources(tmp_path)
    path = tmp_path / "dup.txt"
    path.write_text("same\nsame\n", encoding="utf-8")

    edit = bind_edit.bind(resources)
    try:
        edit({"path": "dup.txt", "edits": [{"oldText": "same", "newText": "other"}]})
    except RuntimeError as e:
        assert "oldText must match exactly once" in str(e)
    else:
        raise AssertionError("expected duplicate oldText to be rejected")


def test_bash_runs_in_working_dir(tmp_path: Path) -> None:
    resources = _resources(tmp_path)
    (tmp_path / "marker.txt").write_text("hello", encoding="utf-8")

    bash = bind_bash.bind(resources)
    result = bash({"command": "pwd && ls marker.txt", "timeout": 5})

    assert result["ok"] is True
    assert str(tmp_path) in result["stdout"]
    assert "marker.txt" in result["stdout"]
