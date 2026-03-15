from __future__ import annotations

import json
from pathlib import Path

from runtime.tools.bindings.world_apply_ops import bind
from runtime.tools.resources import ToolResources


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        _ = limit
        return []


def test_world_apply_ops_accepts_stringified_ops_array(tmp_path: Path) -> None:
    world_path = tmp_path / "world.json"
    world_path.write_text("{}", encoding="utf-8")

    handler = bind(
        ToolResources(
            chat_history=_StubChatHistory(),
            world_state_path=world_path,
            now_iso="2026-03-15T15:08:37+02:00",
            tz="Africa/Windhoek",
        )
    )

    result = handler(
        {
            "ops": json.dumps(
                [
                    {
                        "op": "add",
                        "path": "/topics",
                        "value": ["oil and gas industry"],
                    }
                ]
            )
        }
    )

    assert result["ok"] is True
    assert result["world"]["topics"] == ["oil and gas industry"]
