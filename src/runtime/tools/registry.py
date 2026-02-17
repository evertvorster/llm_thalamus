from __future__ import annotations

import json
from typing import Dict

from runtime.providers.types import ToolDef
from runtime.tool_loop import ToolHandler, ToolSet


def build_default_toolset() -> ToolSet:
    """
    Default toolset used for capability testing / spike nodes.

    IMPORTANT: Do NOT enable this globally in production nodes unless you want tools everywhere.
    Nodes should pass ToolSet explicitly.
    """
    defs = [
        ToolDef(
            name="echo",
            description="Echo back the provided text. Useful for testing tool calls.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    ]

    def echo_handler(args_json: str) -> str:
        obj = json.loads(args_json) if args_json else {}
        return json.dumps({"echo": obj.get("text", "")}, ensure_ascii=False)

    handlers: Dict[str, ToolHandler] = {
        "echo": echo_handler,
    }

    return ToolSet(defs=defs, handlers=handlers)
