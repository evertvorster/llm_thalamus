from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ChatHistoryService(Protocol):
    def tail(self, *, limit: int) -> list[object]:
        """Return the most recent chat turns.

        Concrete return type is intentionally loose here; tool bindings normalize
        to plain JSON-serializable objects.
        """


@dataclass(frozen=True)
class ToolResources:
    """Concrete resources that tool bindings close over.

    These are runtime-only (not serializable) and are constructed by the controller/worker.
    """

    chat_history: ChatHistoryService

    # World-state persistence (optional until a world tool is actually used).
    # Tools that require world mutation MUST fail loudly if these are missing.
    world_state_path: Path | None = None
    now_iso: str = ""
    tz: str = ""
