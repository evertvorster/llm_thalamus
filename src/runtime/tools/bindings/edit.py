from __future__ import annotations

from runtime.tools.bindings._fs_common import resolve_path
from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("edit: args must be an object")
        path = resolve_path(resources, args.get("path"))
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_file():
            raise RuntimeError(f"not a file: {path}")
        edits = args.get("edits")
        if not isinstance(edits, list) or not edits:
            raise ValueError("edit: edits must be a non-empty array")

        original = path.read_text(encoding="utf-8", errors="replace")
        ranges: list[tuple[int, int, str, str]] = []
        for idx, item in enumerate(edits):
            if not isinstance(item, dict):
                raise ValueError("edit: each edit must be an object")
            old = item.get("oldText")
            new = item.get("newText")
            if not isinstance(old, str) or old == "":
                raise ValueError(f"edit[{idx}]: oldText must be a non-empty string")
            if not isinstance(new, str):
                raise ValueError(f"edit[{idx}]: newText must be a string")
            count = original.count(old)
            if count != 1:
                raise RuntimeError(f"edit[{idx}]: oldText must match exactly once; found {count}")
            start = original.index(old)
            end = start + len(old)
            ranges.append((start, end, old, new))

        ranges_sorted = sorted(ranges, key=lambda r: r[0])
        prev_end = -1
        for start, end, _old, _new in ranges_sorted:
            if start < prev_end:
                raise RuntimeError("edit: edits overlap")
            prev_end = end

        parts: list[str] = []
        cursor = 0
        for start, end, _old, new in ranges_sorted:
            parts.append(original[cursor:start])
            parts.append(new)
            cursor = end
        parts.append(original[cursor:])
        updated = "".join(parts)
        path.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": str(path), "edits_applied": len(ranges_sorted)}

    return handler
