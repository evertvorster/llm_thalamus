from __future__ import annotations

# Node -> allowed skills allowlist.
# This is the capability firewall: nodes can only access tools exposed by these skills.

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # Router runs once and may do a small mechanical prefill (chat tail + memory read)
    # before invoking the LLM.
    "router": {"core_context", "mcp_memory_read"},

    # Context builder can assemble context from core sources and MCP memory reads.
    "context_builder": {"core_context", "mcp_memory_read"},

    # Memory retriever reads memories only.
    "memory_retriever": {"mcp_memory_read"},

    # World modifier gets only world ops.
    "world_modifier": {"core_world"},

    # Memory writer writes memories only.
    "memory_writer": {"mcp_memory_write"},
}
