from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from controller.chat_history import ChatTurn, read_tail


@dataclass(frozen=True)
class FileChatHistoryService:
    """Worker-backed chat history service.

    This keeps persistence details (JSONL file) out of runtime nodes and tools.
    """

    history_file: Path

    def tail(self, *, limit: int) -> list[ChatTurn]:
        return read_tail(history_file=self.history_file, limit=limit)
