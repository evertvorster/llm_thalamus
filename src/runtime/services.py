from __future__ import annotations

from dataclasses import dataclass

from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


@dataclass(frozen=True)
class RuntimeServices:
    """Runtime-only services passed into node factories at graph build time.

    This is intentionally NOT part of State (must remain JSON-serializable) and is
    intentionally NOT stored on Deps (to keep provider/prompt config separate from
    capability wiring).
    """

    tools: RuntimeToolkit
    tool_resources: ToolResources
