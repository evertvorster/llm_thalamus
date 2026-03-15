from __future__ import annotations

from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubMCPClient:
    def server_ids(self) -> tuple[str, ...]:
        return ("openmemory",)

    def call_tool(
        self,
        server_id: str,
        *,
        name: str,
        arguments: dict[str, object],
        request_id: int = 10,
    ) -> object:
        raise NotImplementedError


def test_primary_agent_gets_full_discovered_openmemory_tool_surface() -> None:
    openmemory_schema = {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
            "hard_delete": {"type": "boolean"},
        },
        "required": ["memory_id"],
    }
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        mcp=_StubMCPClient(),
        mcp_tool_catalog={
            "openmemory": [
                {
                    "name": "openmemory_query",
                    "description": "Query semantic memory",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "approval": "auto",
                },
                {
                    "name": "openmemory_store",
                    "description": "Store a memory",
                    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                    "approval": "ask",
                },
                {
                    "name": "openmemory_get",
                    "description": "Get a memory",
                    "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}}},
                    "approval": "ask",
                },
                {
                    "name": "openmemory_list",
                    "description": "List memories",
                    "inputSchema": {"type": "object", "properties": {"limit": {"type": "number"}}},
                    "approval": "ask",
                },
                {
                    "name": "openmemory_reinforce",
                    "description": "Reinforce a memory",
                    "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}}},
                    "approval": "ask",
                },
                {
                    "name": "openmemory_delete",
                    "description": "Delete a memory",
                    "inputSchema": openmemory_schema,
                    "approval": "ask",
                },
            ]
        },
    )

    toolkit = RuntimeToolkit(resources=resources)
    toolset = toolkit.toolset_for_node("primary_agent")

    assert set(toolset.handlers.keys()) >= {
        "chat_history_tail",
        "world_apply_ops",
        "openmemory_query",
        "openmemory_store",
        "openmemory_get",
        "openmemory_list",
        "openmemory_reinforce",
        "openmemory_delete",
    }
    assert "route_node" not in toolset.handlers
    assert "context_apply_ops" not in toolset.handlers
    assert toolset.descriptors["openmemory_delete"].parameters == openmemory_schema


def test_context_builder_retains_narrow_openmemory_exposure() -> None:
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        mcp=_StubMCPClient(),
        mcp_tool_catalog={
            "openmemory": [
                {
                    "name": "openmemory_query",
                    "description": "Query semantic memory",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "approval": "auto",
                },
                {
                    "name": "openmemory_delete",
                    "description": "Delete a memory",
                    "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}}},
                    "approval": "ask",
                },
            ]
        },
    )

    toolkit = RuntimeToolkit(resources=resources)
    toolset = toolkit.toolset_for_node("context_builder")

    assert "openmemory_query" in toolset.handlers
    assert "openmemory_delete" not in toolset.handlers
