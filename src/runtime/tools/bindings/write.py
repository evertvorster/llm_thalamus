from __future__ import annotations

from runtime.tools.bindings._fs_common import resolve_path
from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("write: args must be an object")
        content = args.get("content")
        if not isinstance(content, str):
            raise ValueError("write: content must be a string")
        path = resolve_path(resources, args.get("path"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": len(content.encode("utf-8"))}

    return handler
