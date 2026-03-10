from __future__ import annotations

import json
from typing import Any

from runtime.tools.descriptor import BoundTool, ToolDescriptor
from runtime.tools.providers.base import ToolProvider
from runtime.tools.resources import MCPServerBinding, MCPToolBinding, ToolResources


def _parse_json_text(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_text_blocks(content: list[dict[str, Any]] | None) -> list[str]:
    parts: list[str] = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return parts


def normalize_openmemory_query(result: Any) -> dict[str, Any]:
    raw = _as_dict(getattr(result, "raw", None))
    text = str(getattr(result, "text", "") or "")
    content = getattr(result, "content", None)

    parsed = _parse_json_text(text)
    if parsed is None:
        blocks = [_parse_json_text(part) for part in _extract_text_blocks(content)]
        blocks = [b for b in blocks if b is not None]
        parsed = blocks[0] if len(blocks) == 1 else blocks

    items: list[Any] = []
    meta: dict[str, Any] = {
        "server_id": "openmemory",
        "remote_name": "openmemory_query",
        "status": getattr(result, "status", None),
        "duration_ms": getattr(result, "duration_ms", None),
    }

    if isinstance(parsed, dict):
        if isinstance(parsed.get("items"), list):
            items = list(parsed.get("items") or [])
            meta.update(_as_dict(parsed.get("meta")))
        elif isinstance(parsed.get("results"), list):
            items = list(parsed.get("results") or [])
        elif isinstance(parsed.get("memories"), list):
            items = list(parsed.get("memories") or [])
        elif isinstance(parsed.get("data"), list):
            items = list(parsed.get("data") or [])
        elif parsed:
            items = [parsed]
    elif isinstance(parsed, list):
        items = list(parsed)
    elif text:
        items = [{"text": text}]

    if not items and raw:
        items = [_as_dict(raw.get("result")) or raw]

    return {
        "kind": "memory_query",
        "title": "Memory Recall",
        "items": items,
        "meta": meta,
    }


def normalize_openmemory_store(result: Any) -> dict[str, Any]:
    raw = _as_dict(getattr(result, "raw", None))
    text = str(getattr(result, "text", "") or "")
    parsed = _parse_json_text(text)
    payload: dict[str, Any] = {
        "ok": bool(getattr(result, "ok", False)),
        "status": getattr(result, "status", None),
        "duration_ms": getattr(result, "duration_ms", None),
    }
    if isinstance(parsed, dict):
        payload.update(parsed)
    elif text:
        payload["returned"] = text
    elif raw:
        payload["returned"] = raw
    return payload


class MCPToolProvider(ToolProvider):
    def __init__(self, resources: ToolResources):
        self._resources = resources

    def list_tools(self) -> list[BoundTool]:
        if self._resources.mcp is None:
            return []

        out: list[BoundTool] = []
        for server_id, server_binding in sorted(self._resources.mcp_servers.items()):
            tools = self._resources.mcp.list_tools(server_id, refresh=False)
            for spec in tools:
                bt = self._build_bound_tool(server_binding=server_binding, spec=spec)
                if bt is not None:
                    out.append(bt)
        return out

    def _build_bound_tool(
        self,
        *,
        server_binding: MCPServerBinding,
        spec: dict[str, Any],
    ) -> BoundTool | None:
        remote_name = str(spec.get("name") or "").strip()
        if not remote_name:
            return None

        binding = server_binding.tool_bindings.get(remote_name)
        if binding is None and not server_binding.expose_unbound_tools:
            return None

        public_name = (binding.public_name if binding else None) or remote_name
        description = (binding.description_override if binding else None) or str(spec.get("description") or "")
        parameters = (binding.parameters_override if binding else None) or spec.get("inputSchema") or spec.get("parameters") or {
            "type": "object",
            "properties": {},
        }

        descriptor = ToolDescriptor(
            public_name=public_name,
            description=description,
            parameters=parameters,
            kind="mcp",
            server_id=server_binding.server_id,
            remote_name=remote_name,
        )

        def handler(args: dict[str, Any], *, _server_id: str = server_binding.server_id, _remote_name: str = remote_name, _binding: MCPToolBinding | None = binding) -> Any:
            if self._resources.mcp is None:
                raise RuntimeError("MCP client is not configured")

            payload = dict(_binding.argument_defaults) if _binding is not None else {}
            payload.update(args)
            result = self._resources.mcp.call_tool(_server_id, name=_remote_name, arguments=payload)

            if _binding is not None and _binding.result_normalizer is not None:
                return _binding.result_normalizer(result)
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
