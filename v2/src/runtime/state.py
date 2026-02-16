from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class State:
    """
    Minimal bootstrap state for the two-node graph:
      - router decides a route
      - answer produces assistant_text
    """
    user_text: str

    # Router output
    route: Optional[str] = None
    route_confidence: Optional[str] = None  # "low|medium|high"

    # Answer output
    assistant_text: Optional[str] = None

    # Optional scratchpad for later expansion (bundles, metrics, etc.)
    scratch: Dict[str, Any] = field(default_factory=dict)
