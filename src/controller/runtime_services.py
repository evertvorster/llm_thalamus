from __future__ import annotations

from pathlib import Path

from controller.chat_history_service import FileChatHistoryService
from controller.mcp.client import MCPClient, MCPServerConfig

from runtime.services import RuntimeServices
from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


def build_runtime_services(
    *,
    history_file: Path,
    world_state_path: Path | None = None,
    now_iso: str = "",
    tz: str = "",
    # MCP config (optional)
    mcp_openmemory_url: str | None = None,
    mcp_openmemory_api_key: str | None = None,
    mcp_protocol_version: str = "2025-06-18",
) -> RuntimeServices:
    """Construct runtime-only services (tools/resources).

    This is intentionally outside of config; capabilities are wired in code.

    world_state_path/now_iso/tz are optional for now to avoid breaking callers.
    World-mutation tools must fail loudly if called without them.

    MCP is optional; when enabled, we currently wire only OpenMemory over streamable-http.
    """

    chat_history = FileChatHistoryService(history_file=history_file)

    mcp_client = None
    if mcp_openmemory_url and mcp_openmemory_api_key:
        servers = {
            "openmemory": MCPServerConfig(
                server_id="openmemory",
                url=mcp_openmemory_url,
                headers={"X-API-Key": mcp_openmemory_api_key},
                protocol_version=mcp_protocol_version,
                client_name="llm_thalamus",
                client_version="0.0.1",
            )
        }
        mcp_client = MCPClient(servers=servers)

    tool_resources = ToolResources(
        chat_history=chat_history,
        world_state_path=world_state_path,
        now_iso=now_iso,
        tz=tz,
        mcp=mcp_client,
    )
    tools = RuntimeToolkit(resources=tool_resources)
    return RuntimeServices(tools=tools, tool_resources=tool_resources)