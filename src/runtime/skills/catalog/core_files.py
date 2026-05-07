from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "core_files"

TOOL_SELECTORS = (
    ToolSelector(public_name="read"),
    ToolSelector(public_name="write"),
    ToolSelector(public_name="edit"),
    ToolSelector(public_name="bash"),
)
