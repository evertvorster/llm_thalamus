from __future__ import annotations

"""Skill registry (code-level).

Skills are curated bundles of tools and (optionally) capability documentation.
This registry is intentionally outside of the user config file.
"""

# Enabled skill names.
ENABLED_SKILLS: set[str] = {
    "core_context",
    "core_world",
    "mcp_memory_read",
    "mcp_memory_write",
}