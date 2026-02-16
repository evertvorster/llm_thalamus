from __future__ import annotations

# Deterministic discovery: import modules to trigger registration.
from runtime.nodes import llm_answer  # noqa: F401
from runtime.nodes import llm_router  # noqa: F401
