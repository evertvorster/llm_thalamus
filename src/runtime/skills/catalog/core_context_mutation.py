from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "core_context_mutation"

TOOL_SELECTORS = (
    ToolSelector(public_name="context_apply_ops"),
)
