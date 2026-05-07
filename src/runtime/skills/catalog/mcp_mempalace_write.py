from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "mcp_mempalace_write"

TOOL_SELECTORS = (
    ToolSelector(kind="mcp", server_id="mempalace", remote_name="mempalace_add_drawer"),
)
