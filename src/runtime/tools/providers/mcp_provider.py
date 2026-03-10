from __future__ import annotations

from typing import Any

from runtime.tools.descriptor import BoundTool, ToolDescriptor
from runtime.tools.providers.base import ToolProvider
from runtime.tools.resources import ToolResources


class MCPToolProvider(ToolProvider):
    def __init__(self, resources: ToolResources):
        self._resources = resources

    def list_tools(self) -> list[BoundTool]:
        if self._resources.mcp is None:
            return []

        out: list[BoundTool] = []
        for server_id in self._resources.mcp.server_ids():
            tools = self._resources.mcp.list_tools(server_id, refresh=False)
            for spec in tools:
                bt = self._build_bound_tool(server_id=server_id, spec=spec)
                if bt is not None:
                    out.append(bt)
        return out

    def _build_bound_tool(
        self,
        *,
        server_id: str,
        spec: dict[str, Any],
    ) -> BoundTool | None:
        remote_name = str(spec.get("name") or "").strip()
        if not remote_name:
            return None

        public_name = remote_name
        description = str(spec.get("description") or "")
        parameters = spec.get("inputSchema") or spec.get("parameters") or {
            "type": "object",
            "properties": {},
        }

        descriptor = ToolDescriptor(
            public_name=public_name,
            description=description,
            parameters=parameters,
            kind="mcp",
            server_id=server_id,
            remote_name=remote_name,
        )

        def handler(args: dict[str, Any], *, _server_id: str = server_id, _remote_name: str = remote_name) -> Any:
            if self._resources.mcp is None:
                raise RuntimeError("MCP client is not configured")

            result = self._resources.mcp.call_tool(_server_id, name=_remote_name, arguments=args)
            return {
                "ok": bool(getattr(result, "ok", False)),
                "status": getattr(result, "status", None),
                "duration_ms": getattr(result, "duration_ms", None),
                "content": getattr(result, "content", None),
                "text": getattr(result, "text", ""),
                "raw": getattr(result, "raw", None),
                "error": getattr(result, "error", None),
            }

        return BoundTool(descriptor=descriptor, handler=handler, validator=None)
