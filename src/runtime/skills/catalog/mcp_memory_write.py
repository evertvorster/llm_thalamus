from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "mcp_memory_write"

TOOL_SELECTORS = (
    ToolSelector(kind="mcp", server_id="openmemory", remote_name="openmemory_store"),
)
