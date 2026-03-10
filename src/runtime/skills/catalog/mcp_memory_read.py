from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "mcp_memory_read"

TOOL_SELECTORS = (
    ToolSelector(kind="mcp", public_name="memory_query"),
)
