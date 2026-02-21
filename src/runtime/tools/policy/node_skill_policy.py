from __future__ import annotations

"""
Node → allowed skill names (capability firewall).
This is intentionally code-level and separate from config.
"""

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # Context builder can assemble context from core sources and MCP memory reads.
    "context_builder": {"core_context", "mcp_memory_read"},

    # Memory retriever reads memories only.
    "memory_retriever": {"mcp_memory_read"},

    # World modifier gets only world ops.
    "world_modifier": {"core_world"},

    # Memory writer writes memories only.
    "memory_writer": {"mcp_memory_write"},
}