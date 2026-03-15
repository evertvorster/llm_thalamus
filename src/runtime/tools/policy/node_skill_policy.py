from __future__ import annotations

# Node -> allowed skills allowlist.
# This is the capability firewall: nodes can only access tools exposed by these skills.

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # Context bootstrap runs once and mechanically seeds the working transcript.
    "context_bootstrap": {"core_context", "mcp_memory_read"},

    "primary_agent": {
        "core_context",
        "core_world",
        "mcp_openmemory_full",
    },

    # Memory writer writes memories only.
    "reflect": {"core_world", "mcp_memory_write", "core_reflect_completion"},
}
