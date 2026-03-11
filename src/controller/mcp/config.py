from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any

from controller.mcp.client import MCPClient, MCPServerConfig


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_mcp_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"mcp_servers.json not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return normalize_mcp_config(raw)


def save_mcp_config(path: Path, mcp_config: dict[str, Any]) -> None:
    normalized = normalize_mcp_config(mcp_config)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=".mcp_servers.json.",
        dir=path.parent,
        delete=False,
    ) as tf:
        tmp_path = Path(tf.name)

    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists() and tmp_path != path:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def normalize_mcp_config(raw: dict[str, Any]) -> dict[str, Any]:
    servers = raw.get("servers", {}) if isinstance(raw, dict) else {}
    if not isinstance(servers, dict):
        raise ValueError("mcp_servers.json: servers must be an object")

    normalized_servers: dict[str, Any] = {}
    for server_id, server_cfg in servers.items():
        if not isinstance(server_id, str) or not isinstance(server_cfg, dict):
            continue
        normalized_servers[server_id] = _normalize_server_config(server_cfg)

    return {"servers": normalized_servers}


def build_runtime_server_map(mcp_config: dict[str, Any]) -> dict[str, MCPServerConfig]:
    out: dict[str, MCPServerConfig] = {}
    servers = mcp_config.get("servers", {})
    if not isinstance(servers, dict):
        return out

    for server_id, server_cfg in servers.items():
        if not isinstance(server_id, str) or not isinstance(server_cfg, dict):
            continue
        if not bool(server_cfg.get("enabled", False)):
            continue
        status = server_cfg.get("status", {}) or {}
        if not isinstance(status, dict) or not bool(status.get("available", False)):
            continue

        cfg = _server_config_from_struct(server_id, server_cfg)
        if cfg is not None:
            out[server_id] = cfg

    return out


def build_runtime_tool_catalog(mcp_config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    servers = mcp_config.get("servers", {})
    if not isinstance(servers, dict):
        return out

    for server_id, server_cfg in servers.items():
        if not isinstance(server_id, str) or not isinstance(server_cfg, dict):
            continue
        if not bool(server_cfg.get("enabled", False)):
            continue

        status = server_cfg.get("status", {}) or {}
        if not isinstance(status, dict) or not bool(status.get("available", False)):
            continue

        tools = server_cfg.get("tools", {}) or {}
        if not isinstance(tools, dict):
            continue

        runtime_specs: list[dict[str, Any]] = []
        for tool_name, tool_cfg in tools.items():
            if not isinstance(tool_name, str) or not isinstance(tool_cfg, dict):
                continue
            if not bool(tool_cfg.get("available", False)):
                continue

            parameters = tool_cfg.get("input_schema")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}

            runtime_specs.append(
                {
                    "name": tool_name,
                    "description": str(tool_cfg.get("description") or ""),
                    "inputSchema": parameters,
                    "approval": str(tool_cfg.get("approval") or "ask"),
                }
            )

        if runtime_specs:
            out[server_id] = runtime_specs

    return out


def discover_and_reconcile_mcp(mcp_config: dict[str, Any]) -> dict[str, Any]:
    reconciled = normalize_mcp_config(mcp_config)
    servers = reconciled["servers"]
    now = _now_iso_utc()

    for server_id, server_cfg in servers.items():
        if not isinstance(server_cfg, dict):
            continue

        status = server_cfg.setdefault("status", {})
        if not isinstance(status, dict):
            status = {}
            server_cfg["status"] = status

        tools = server_cfg.setdefault("tools", {})
        if not isinstance(tools, dict):
            tools = {}
            server_cfg["tools"] = tools

        status["last_startup_check"] = now
        if not bool(server_cfg.get("enabled", False)):
            status["available"] = False
            status["last_error"] = None
            for tool_cfg in tools.values():
                if isinstance(tool_cfg, dict):
                    tool_cfg["available"] = False
            continue

        try:
            runtime_cfg = _server_config_from_struct(server_id, server_cfg)
            if runtime_cfg is None:
                raise ValueError(f"server '{server_id}' has unsupported or incomplete transport")

            discovered = MCPClient(servers={server_id: runtime_cfg}).list_tools(server_id, refresh=True)
            _reconcile_tools(tools=tools, discovered=discovered, now=now)
            status["available"] = True
            status["last_error"] = None
        except Exception as e:
            status["available"] = False
            status["last_error"] = str(e)
            for tool_cfg in tools.values():
                if isinstance(tool_cfg, dict):
                    tool_cfg["available"] = False

    return reconciled


def _reconcile_tools(*, tools: dict[str, Any], discovered: list[dict[str, Any]], now: str) -> None:
    for tool_cfg in tools.values():
        if isinstance(tool_cfg, dict):
            tool_cfg["available"] = False

    for spec in discovered:
        if not isinstance(spec, dict):
            continue
        tool_name = str(spec.get("name") or "").strip()
        if not tool_name:
            continue

        tool_cfg = tools.get(tool_name)
        is_new = not isinstance(tool_cfg, dict)
        if not isinstance(tool_cfg, dict):
            tool_cfg = {}
            tools[tool_name] = tool_cfg

        tool_cfg["approval"] = str(tool_cfg.get("approval") or "ask")
        if not tool_cfg["approval"]:
            tool_cfg["approval"] = "ask"
        tool_cfg["description"] = str(spec.get("description") or "")
        tool_cfg["input_schema"] = spec.get("inputSchema") or spec.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        tool_cfg["available"] = True
        if is_new or "last_seen" in tool_cfg:
            tool_cfg["last_seen"] = now


def _normalize_server_config(server_cfg: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for key in ("label", "enabled"):
        if key in server_cfg:
            normalized[key] = deepcopy(server_cfg[key])

    transport = server_cfg.get("transport")
    if isinstance(transport, dict):
        normalized["transport"] = deepcopy(transport)

    status = server_cfg.get("status")
    if isinstance(status, dict):
        normalized["status"] = _normalize_server_status(status)

    tools = server_cfg.get("tools")
    if isinstance(tools, dict):
        normalized_tools: dict[str, Any] = {}
        for tool_name, tool_cfg in tools.items():
            if not isinstance(tool_name, str) or not isinstance(tool_cfg, dict):
                continue
            normalized_tools[tool_name] = _normalize_tool_config(tool_cfg)
        normalized["tools"] = normalized_tools

    return normalized


def _normalize_server_status(status: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("available", "last_startup_check", "last_error"):
        if key in status:
            normalized[key] = deepcopy(status[key])
    return normalized


def _normalize_tool_config(tool_cfg: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    approval = str(tool_cfg.get("approval") or "ask").strip() or "ask"
    normalized["approval"] = approval

    if "available" in tool_cfg:
        normalized["available"] = bool(tool_cfg.get("available"))

    return normalized


def _server_config_from_struct(server_id: str, server_cfg: dict[str, Any]) -> MCPServerConfig | None:
    transport = server_cfg.get("transport", {}) or {}
    if not isinstance(transport, dict):
        return None
    if str(transport.get("type") or "") != "streamable-http":
        return None

    url = str(transport.get("url") or "").strip()
    if not url:
        return None

    headers = transport.get("headers", {}) or {}
    if not isinstance(headers, dict):
        headers = {}

    return MCPServerConfig(
        server_id=server_id,
        url=url,
        headers={str(k): str(v) for k, v in headers.items() if isinstance(k, str)},
    )
