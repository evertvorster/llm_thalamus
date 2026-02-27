from __future__ import annotations

from typing import Any
import json

from runtime.tool_loop import ToolArgs, ToolHandler, ToolResult
from runtime.tools.resources import ToolResources


def bind(resources: ToolResources, *, hard_max: int = 200) -> ToolHandler:
    """Bind chat_history_tail to concrete runtime resources.

    NOTE (schema v2):
    This tool returns a typed "source" object compatible with Option A context shape:
      { kind, title, items, meta }
    """

    def _clamp_limit(v: Any) -> int:
        try:
            n = int(v)
        except Exception:
            return 0
        if n < 0:
            return 0
        if n > hard_max:
            return hard_max
        return n

    def handler(args: ToolArgs) -> ToolResult:
        limit = _clamp_limit((args or {}).get("limit", 0))

        turns = resources.chat_history.tail(limit=limit)

        out_turns: list[dict[str, str]] = []
        for t in turns or []:
            # Support controller.chat_history.ChatTurn and plain dict-like objects.
            role = getattr(t, "role", None)
            content = getattr(t, "content", None)
            ts = getattr(t, "ts", None)
            if isinstance(t, dict):
                role = t.get("role")
                content = t.get("content")
                ts = t.get("ts")

            if not isinstance(role, str) or not isinstance(content, str):
                continue

            rec: dict[str, str] = {"role": role, "content": content}
            if isinstance(ts, str) and ts:
                rec["ts"] = ts
            out_turns.append(rec)

        # Schema v2: return a typed source entry (Option A)
        payload = {
            "kind": "chat_turns",
            "title": "Recent chat turns",
            "items": out_turns,
            "meta": {
                "limit": limit,
                "returned": len(out_turns),
            },
        }

        return payload

    return handler