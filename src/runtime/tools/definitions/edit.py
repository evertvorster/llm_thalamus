from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="edit",
        description=(
            "Edit a text file using exact text replacement. Each oldText must match "
            "exactly once in the original file. Use one call with multiple edits for "
            "separate replacements in the same file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to edit."},
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {"type": "string", "description": "Exact text to replace."},
                            "newText": {"type": "string", "description": "Replacement text."},
                        },
                        "required": ["oldText", "newText"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
    )
