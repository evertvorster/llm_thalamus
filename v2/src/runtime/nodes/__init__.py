from __future__ import annotations

# Deterministic discovery: import modules to trigger registration.
# Use *relative* imports to avoid circular import during package init.
from . import llm_router  # noqa: F401
from . import llm_answer  # noqa: F401
