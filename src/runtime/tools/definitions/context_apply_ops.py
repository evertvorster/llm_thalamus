from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="context_apply_ops",
        description=(
            "Apply validated mutations to runtime context. "
            "Supports source upsert/clear and handoff flags."
        ),
        parameters={
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                },
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": [
                                    "upsert_source",
                                    "clear_sources_by_kind",
                                    "set_complete",
                                    "set_next",
                                ],
                            },
                            "kind": {"type": "string"},
                            "source": {"type": "object"},
                            "value": {},
                        },
                        "required": ["op"],
                    },
                },
            },
            "required": ["context", "ops"],
        },
    )
