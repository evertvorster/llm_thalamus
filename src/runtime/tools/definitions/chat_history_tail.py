from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="chat_history_tail",
        description=(
            "Return the most recent chat turns (role/content). "
            "Use this to understand follow-ups and short referential messages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 200,
                    "description": "Maximum number of recent turns to return.",
                }
            },
            "required": ["limit"],
        },
    )
