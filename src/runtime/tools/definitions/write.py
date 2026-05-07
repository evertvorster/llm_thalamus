from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="write",
        description=(
            "Create or overwrite a text file. Relative paths resolve against the "
            "configured working directory. Parent directories are created automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write."},
                "content": {"type": "string", "description": "Complete file contents."},
            },
            "required": ["path", "content"],
        },
    )
