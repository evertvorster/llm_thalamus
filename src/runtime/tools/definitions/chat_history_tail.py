from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="chat_history_tail",
        description=(
            "Return a typed context source containing the most recent chat turns. "
            "The tool returns a JSON object with keys: kind, title, items, meta. "
            "Append this object directly into context.sources."
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