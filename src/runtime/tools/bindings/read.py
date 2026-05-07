from __future__ import annotations

from runtime.tools.bindings._fs_common import resolve_path
from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult

_MAX_CHARS = 50_000
_MAX_LINES = 2_000


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("read: args must be an object")
        path = resolve_path(resources, args.get("path"))
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_file():
            raise RuntimeError(f"not a file: {path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        offset = int(args.get("offset") or 1)
        limit = int(args.get("limit") or _MAX_LINES)
        if offset < 1:
            raise ValueError("read: offset must be >= 1")
        if limit < 1:
            raise ValueError("read: limit must be >= 1")
        limit = min(limit, _MAX_LINES)
        selected = lines[offset - 1 : offset - 1 + limit]
        out = "".join(selected)
        truncated = False
        if len(out) > _MAX_CHARS:
            out = out[:_MAX_CHARS]
            truncated = True
        if offset - 1 + limit < len(lines):
            truncated = True
        return {
            "ok": True,
            "path": str(path),
            "content": out,
            "line_count": len(lines),
            "offset": offset,
            "limit": limit,
            "truncated": truncated,
        }

    return handler
