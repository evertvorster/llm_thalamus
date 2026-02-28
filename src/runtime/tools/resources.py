from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ChatHistoryService(Protocol):
    def tail(self, *, limit: int) -> list[object]:
        ...


class MCPClient(Protocol):
    def call_tool(
        self,
        server_id: str,
        *,
        name: str,
        arguments: dict[str, Any],
        request_id: int = 10,
    ) -> Any:
        ...


@dataclass(frozen=True)
class ToolResources:
    chat_history: ChatHistoryService

    # World-state persistence
    world_state_path: Path | None = None
    now_iso: str = ""
    tz: str = ""

    # MCP wiring
    mcp: MCPClient | None = None
    # OpenMemory tenant/user namespace (NOT LLM-controlled). Derived from OpenMemory X-API-Key.
    mcp_openmemory_user_id: str = "llm_thalamus"