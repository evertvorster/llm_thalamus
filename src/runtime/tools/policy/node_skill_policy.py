from __future__ import annotations

# Node -> allowed skills allowlist.
# This is the capability firewall: nodes can only access tools exposed by these skills.

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # Context bootstrap runs once and may do a small mechanical prefill
    # (chat tail + memory read) before handing off to the context builder.
    "context_bootstrap": {"core_context", "core_context_mutation", "mcp_memory_read"},

    # Context builder can assemble context from core sources and MCP memory reads.
    "context_builder": {"core_context", "mcp_memory_read", "core_world"},

    # Memory writer writes memories only.
    "reflect": {"core_world", "mcp_memory_write"},
}
