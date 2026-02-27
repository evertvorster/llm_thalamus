from __future__ import annotations

from typing import Any

from runtime.tool_loop import ToolArgs, ToolHandler, ToolResult
from runtime.tools.resources import ToolResources


def bind(resources: ToolResources, *, hard_max: int = 200) -> ToolHandler:
    """Bind chat_history_tail to concrete runtime resources.

    NOTE (schema v2):
    This tool returns a typed "source" object compatible with Option A context shape:
      { kind, title, items, meta }

    Option 4 behavior:
    Treat "history" as complete turns: if the tail ends on a USER message,
    drop that final USER message so the returned history ends on ASSISTANT.
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
        if limit <= 0:
            return {
                "kind": "chat_turns",
                "title": "Recent chat turns",
                "items": [],
                "meta": {
                    "limit": limit,
                    "returned": 0,
                    "fetch_limit": 0,
                    "trimmed_last_user": False,
                },
            }

        # Fetch one extra turn so that if we trim a trailing USER message,
        # we can still try to satisfy the requested `limit`.
        fetch_limit = _clamp_limit(limit + 1)
        turns = resources.chat_history.tail(limit=fetch_limit)

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

        trimmed_last_user = False
        if out_turns and out_turns[-1].get("role") == "user":
            out_turns.pop()
            trimmed_last_user = True

        # Respect the caller's requested limit.
        if len(out_turns) > limit:
            out_turns = out_turns[-limit:]

        # Schema v2: return a typed source entry (Option A)
        payload = {
            "kind": "chat_turns",
            "title": "Recent chat turns",
            "items": out_turns,
            "meta": {
                "limit": limit,
                "returned": len(out_turns),
                "fetch_limit": fetch_limit,
                "trimmed_last_user": trimmed_last_user,
            },
        }

        return payload

    return handler