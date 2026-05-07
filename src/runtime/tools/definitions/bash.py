from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="bash",
        description=(
            "Execute a bash command in the configured working directory. Returns stdout, "
            "stderr, and exit code. Use for shell commands, tests, grep/rg/find, and other "
            "project operations."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute."},
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 600,
                    "description": "Optional timeout in seconds. Default 60.",
                },
            },
            "required": ["command"],
        },
    )
