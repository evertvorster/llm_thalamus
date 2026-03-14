from __future__ import annotations

from pathlib import Path

from controller.chat_history_service import FileChatHistoryService
from controller.mcp.client import MCPClient, MCPServerConfig

from runtime.services import RuntimeServices
from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit
from runtime.tools.types import ToolApprovalRequester


def build_runtime_services(
    *,
    history_file: Path,
    world_state_path: Path | None = None,
    now_iso: str = "",
    tz: str = "",
    prefill_chat_history_limit: int = 4,
    prefill_memory_k: int = 6,
    mcp_servers: dict[str, MCPServerConfig] | None = None,
    mcp_tool_catalog: dict[str, list[dict[str, object]]] | None = None,
    internal_tool_policy: dict[str, dict[str, object]] | None = None,
    tool_approval_requester: ToolApprovalRequester | None = None,
) -> RuntimeServices:
    chat_history = FileChatHistoryService(history_file=history_file)

    server_map = dict(mcp_servers or {})
    mcp_client = MCPClient(servers=server_map) if server_map else None

    tool_resources = ToolResources(
        chat_history=chat_history,
        world_state_path=world_state_path,
        now_iso=now_iso,
        tz=tz,
        prefill_chat_history_limit=int(prefill_chat_history_limit),
        prefill_memory_k=int(prefill_memory_k),
        mcp=mcp_client,
        mcp_tool_catalog={k: list(v) for k, v in dict(mcp_tool_catalog or {}).items()} or None,
        internal_tool_policy={k: dict(v) for k, v in dict(internal_tool_policy or {}).items()} or None,
        tool_approval_requester=tool_approval_requester,
    )
    tools = RuntimeToolkit(resources=tool_resources)
    return RuntimeServices(tools=tools, tool_resources=tool_resources)
