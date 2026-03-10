from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


class ChatHistoryService(Protocol):
    def tail(self, *, limit: int) -> list[object]:
        ...


class MCPClient(Protocol):
    def list_tools(self, server_id: str, *, refresh: bool = False) -> list[dict[str, Any]]:
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


MCPResultNormalizer = Callable[[Any], Any]


@dataclass(frozen=True)
class MCPToolBinding:
    remote_name: str
    public_name: str | None = None
    argument_defaults: dict[str, Any] = field(default_factory=dict)
    result_normalizer: MCPResultNormalizer | None = None
    description_override: str | None = None
    parameters_override: dict[str, Any] | None = None


@dataclass(frozen=True)
class MCPServerBinding:
    server_id: str
    tool_bindings: dict[str, MCPToolBinding] = field(default_factory=dict)
    expose_unbound_tools: bool = False


@dataclass(frozen=True)
class ToolResources:
    chat_history: ChatHistoryService

    # World-state persistence
    world_state_path: Path | None = None
    now_iso: str = ""
    tz: str = ""

    # MCP wiring
    mcp: MCPClient | None = None
    mcp_servers: dict[str, MCPServerBinding] = field(default_factory=dict)
