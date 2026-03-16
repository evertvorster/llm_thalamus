from __future__ import annotations

from runtime.tools.types import ToolArgs, ToolResult
from runtime.tools.resources import ToolResources


def bind(resources: ToolResources):
    _ = resources

    def _handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("answer_user: args must be an object")
        content = str(args.get("content") or "").strip()
        if not content:
            raise ValueError("answer_user: 'content' must be a non-empty string")
        return {"ok": True, "content": content}

    return _handler
