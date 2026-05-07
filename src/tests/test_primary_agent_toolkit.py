from __future__ import annotations

from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


class _StubChatHistory:
    def tail(self, *, limit: int) -> list[object]:
        return []


class _StubMCPClient:
    def server_ids(self) -> tuple[str, ...]:
        return ("mempalace",)

    def call_tool(
        self,
        server_id: str,
        *,
        name: str,
        arguments: dict[str, object],
        request_id: int = 10,
    ) -> object:
        raise NotImplementedError


def test_primary_agent_gets_full_discovered_mempalace_tool_surface() -> None:
    add_schema = {
        "type": "object",
        "properties": {
            "wing": {"type": "string"},
            "room": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["wing", "room", "content"],
    }
    resources = ToolResources(
        chat_history=_StubChatHistory(),
        mcp=_StubMCPClient(),
        mcp_tool_catalog={
            "mempalace": [
                {
                    "name": "mempalace_search",
                    "description": "Search semantic memory",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                    "approval": "auto",
                },
                {
                    "name": "mempalace_add_drawer",
                    "description": "File verbatim content",
                    "inputSchema": add_schema,
                    "approval": "ask",
                },
                {
                    "name": "mempalace_kg_query",
                    "description": "Query facts",
                    "inputSchema": {"type": "object", "properties": {"entity": {"type": "string"}}},
                    "approval": "auto",
                },
            ]
        },
    )

    toolkit = RuntimeToolkit(resources=resources)
    toolset = toolkit.toolset_for_node("primary_agent")

    assert set(toolset.handlers.keys()) >= {
        "chat_history_tail",
        "world_apply_ops",
        "read",
        "write",
        "edit",
        "bash",
        "mempalace_search",
        "mempalace_add_drawer",
        "mempalace_kg_query",
    }
    assert "context_apply_ops" not in toolset.handlers
    assert toolset.descriptors["mempalace_add_drawer"].parameters == add_schema
