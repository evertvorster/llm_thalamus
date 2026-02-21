from __future__ import annotations

"""Node -> allowed skills policy.

This is a code-level capability allowlist, intentionally outside of the user config.
"""

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # LangGraph node key -> allowed skills

    # Context builder can read chat tail + durable memory.
    "context_builder": {"core_context", "mcp_memory_read"},

    # World modifier can apply world ops.
    "world_modifier": {"core_world"},

    # Future: memory writer node should be the only place allowed to write durable memory.
    # "mcp_memory_writer": {"mcp_memory_write"},
}