from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="read",
        description=(
            "Read the contents of a text file. Relative paths resolve against the "
            "configured working directory. Use offset/limit for large files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read."},
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional 1-indexed line number to start reading from.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2000,
                    "description": "Optional maximum number of lines to return.",
                },
            },
            "required": ["path"],
        },
    )
