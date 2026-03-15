from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "mcp_openmemory_full"

TOOL_SELECTORS = (
    ToolSelector(kind="mcp", server_id="openmemory"),
)
