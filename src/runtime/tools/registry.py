from __future__ import annotations

import json
from typing import Dict

from runtime.providers.types import ToolDef
from runtime.tool_loop import ToolArgs, ToolHandler, ToolResult, ToolSet, ToolValidator


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

    def echo_handler(args: ToolArgs) -> ToolResult:
        obj = args or {}
        return {"echo": obj.get("text", "")}

    def _validate_echo(res: ToolResult) -> None:
        if not isinstance(res, dict) or "echo" not in res:
            raise ValueError("echo tool must return an object with key 'echo'")

    handlers: Dict[str, ToolHandler] = {
        "echo": echo_handler,
    }
    validators: Dict[str, ToolValidator] = {
        "echo": _validate_echo,
    }

    return ToolSet(defs=defs, handlers=handlers, validators=validators)
