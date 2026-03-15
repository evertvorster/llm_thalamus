from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from runtime.tools.types import ToolApprovalRequester

class ChatHistoryService(Protocol):
    def tail(self, *, limit: int) -> list[object]:
        ...


class MCPClient(Protocol):
    def server_ids(self) -> tuple[str, ...]:
        ...

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
    prefill_chat_history_limit: int = 4
    prefill_shared_memory_k: int = 2
    prefill_user_memory_k: int = 2
    prefill_agent_memory_k: int = 2

    # MCP wiring
    mcp: MCPClient | None = None
    mcp_tool_catalog: dict[str, list[dict[str, Any]]] | None = None
    internal_tool_policy: dict[str, dict[str, Any]] | None = None
    tool_approval_requester: ToolApprovalRequester | None = None
