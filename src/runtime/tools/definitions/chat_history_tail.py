from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="chat_history_tail",
        description=(
            "Return retrieval data for the most recent chat turns. "
            "This tool is retrieval-only and does not mutate runtime context."
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
