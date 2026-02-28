from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="memory_store",
        description=(
            "Store durable semantic/temporal memory via OpenMemory (MCP). "
            "Use only for high-signal, cross-session useful info."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Raw memory text to store.",
                },
                "type": {
                    "type": "string",
                    "enum": ["contextual", "factual", "both"],
                    "default": "contextual",
                    "description": (
                        "Storage type: 'contextual' (default), 'factual' (facts only), or 'both'."
                    ),
                },
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string", "minLength": 1},
                            "predicate": {"type": "string", "minLength": 1},
                            "object": {"type": "string", "minLength": 1},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "valid_from": {"type": "string"},
                        },
                        "required": ["subject", "predicate", "object"],
                        "additionalProperties": False,
                    },
                    "description": (
                        "Facts to store (required when type is 'factual' or 'both' on the server side)."
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags (contextual storage).",
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Optional metadata blob.",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    )
