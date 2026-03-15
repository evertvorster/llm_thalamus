from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="route_node",
        description=(
            "Request orchestration handoff from the current controller node. "
            "Carries only route target and handoff status metadata."
        ),
        parameters={
            "type": "object",
            "properties": {
                "node": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["complete", "incomplete", "blocked"],
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "handoff_note": {"type": "string"},
            },
            "required": ["node", "status"],
        },
    )
