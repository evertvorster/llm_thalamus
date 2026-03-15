from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="reflect_complete",
        description=(
            "Signal reflect-node completion with summary payload. "
            "This tool does not mutate context or world state."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "stored": {
                    "type": "array",
                    "items": {},
                },
                "stored_count": {"type": "number"},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "notes": {"type": "string"},
            },
            "required": ["topics", "stored", "stored_count"],
        },
    )
