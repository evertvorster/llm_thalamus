from __future__ import annotations

from runtime.tools.descriptor import ToolSelector

SKILL_NAME = "core_answer"

TOOL_SELECTORS = (
    ToolSelector(public_name="answer_user"),
)
