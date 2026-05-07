from __future__ import annotations

import json
import sys
from pathlib import Path

from controller.mcp.client import MCPClient
from controller.mcp.config import build_runtime_server_map, build_runtime_tool_catalog, discover_and_reconcile_mcp


def test_stdio_mcp_discovery_and_tool_call(tmp_path: Path) -> None:
    server = tmp_path / "fake_mcp.py"
    server.write_text(
        """
import json
import sys

TOOLS = [{
    "name": "demo_echo",
    "description": "Echo a value",
    "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
}]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    method = req.get("method")
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"tools": TOOLS}}
    elif method == "tools/call":
        args = (req.get("params") or {}).get("arguments") or {}
        resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"content": [{"type": "text", "text": args.get("value", "")}]} }
    else:
        resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"message": "unknown"}}
    print(json.dumps(resp), flush=True)
""".strip(),
        encoding="utf-8",
    )

    cfg = {
        "servers": {
            "fake": {
                "enabled": True,
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(server)],
                },
                "tools": {},
            }
        }
    }

    reconciled = discover_and_reconcile_mcp(cfg)
    assert reconciled["servers"]["fake"]["status"]["available"] is True
    assert reconciled["servers"]["fake"]["tools"]["demo_echo"]["available"] is True

    runtime_servers = build_runtime_server_map(reconciled)
    runtime_catalog = build_runtime_tool_catalog(reconciled)
    assert "fake" in runtime_servers
    assert runtime_catalog["fake"][0]["name"] == "demo_echo"

    client = MCPClient(servers=runtime_servers)
    result = client.call_tool("fake", name="demo_echo", arguments={"value": "hello"})
    assert result.ok is True
    assert result.text == "hello"
