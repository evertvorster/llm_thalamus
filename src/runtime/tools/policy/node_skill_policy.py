from __future__ import annotations

"""Node -> allowed skills policy.

This is a code-level capability allowlist, intentionally outside of the user config.
"""

NODE_ALLOWED_SKILLS: dict[str, set[str]] = {
    # LangGraph node key -> allowed skills
    "context_builder": {"core_context"},
}
