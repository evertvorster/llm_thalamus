from __future__ import annotations

"""Core context-building tools.

The goal of this skill is to help nodes build high-quality context (chat history,
later memories/episodes) without embedding persistence details into nodes.
"""

SKILL_NAME = "core_context"

# Tool names included in this skill.
TOOL_NAMES: set[str] = {
    "chat_history_tail",
}
