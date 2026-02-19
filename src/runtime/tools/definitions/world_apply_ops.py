from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="world_apply_ops",
        description=(
            "Apply validated modifications to the persistent world state. "
            "Supports set, add, and remove operations on allowlisted paths."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["set", "add", "remove"],
                            },
                            "path": {
                                "type": "string",
                                "description": "JSON pointer-style path, e.g. /project or /goals",
                            },
                            "value": {}
                        },
                        "required": ["op", "path"],
                    },
                }
            },
            "required": ["ops"],
        },
    )
