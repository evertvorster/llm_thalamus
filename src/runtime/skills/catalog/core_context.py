from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "core_context"

TOOL_SELECTORS = (
    ToolSelector(public_name="chat_history_tail"),
)
