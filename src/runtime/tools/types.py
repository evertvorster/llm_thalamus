from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


ToolArgs = dict[str, Any]
ToolResult = Any
ToolHandler = Callable[[ToolArgs], ToolResult]
ToolValidator = Callable[[ToolResult], None]
ToolApprovalMode = Literal["auto", "ask", "deny"]


@dataclass(frozen=True)
class ToolApprovalRequest:
    tool_name: str
    args: ToolArgs
    tool_kind: str | None = None
    description: str = ""
    node_id: str | None = None
    span_id: str | None = None
    step: int | None = None
    tool_call_id: str | None = None
    mcp_server_id: str | None = None
    mcp_remote_name: str | None = None


ToolApprovalRequester = Callable[[ToolApprovalRequest], bool]
