from __future__ import annotations

from pathlib import Path

from controller.chat_history_service import FileChatHistoryService
from controller.mcp.client import MCPClient, MCPServerConfig

from runtime.services import RuntimeServices
from runtime.tools.resources import MCPServerBinding, MCPToolBinding, ToolResources
from runtime.tools.toolkit import RuntimeToolkit
from runtime.tools.providers.mcp_provider import normalize_openmemory_query, normalize_openmemory_store


def build_runtime_services(
    *,
    history_file: Path,
    world_state_path: Path | None = None,
    now_iso: str = "",
    tz: str = "",
    mcp_servers: dict[str, MCPServerConfig] | None = None,
) -> RuntimeServices:
    chat_history = FileChatHistoryService(history_file=history_file)

    server_map = dict(mcp_servers or {})
    mcp_client = MCPClient(servers=server_map) if server_map else None

    mcp_bindings: dict[str, MCPServerBinding] = {}
    if "openmemory" in server_map:
        api_key = str((server_map["openmemory"].headers or {}).get("X-API-Key") or "llm_thalamus")
        mcp_bindings["openmemory"] = MCPServerBinding(
            server_id="openmemory",
            expose_unbound_tools=False,
            tool_bindings={
                "openmemory_query": MCPToolBinding(
                    remote_name="openmemory_query",
                    public_name="memory_query",
                    argument_defaults={"user_id": api_key},
                    result_normalizer=normalize_openmemory_query,
                ),
                "openmemory_store": MCPToolBinding(
                    remote_name="openmemory_store",
                    public_name="memory_store",
                    argument_defaults={"user_id": api_key},
                    result_normalizer=normalize_openmemory_store,
                ),
            },
        )

    tool_resources = ToolResources(
        chat_history=chat_history,
        world_state_path=world_state_path,
        now_iso=now_iso,
        tz=tz,
        mcp=mcp_client,
        mcp_servers=mcp_bindings,
    )
    tools = RuntimeToolkit(resources=tool_resources)
    return RuntimeServices(tools=tools, tool_resources=tool_resources)
