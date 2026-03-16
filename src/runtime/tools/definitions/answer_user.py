from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="answer_user",
        description="Send the final user-facing answer for the current turn.",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The exact final reply to show to the user.",
                }
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    )
