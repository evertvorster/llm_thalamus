from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from controller.mcp.transport_streamable_http import StreamableHttpTransport


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    url: str
    headers: dict[str, str]
    protocol_version: str = "2025-06-18"
    client_name: str = "llm_thalamus"
    client_version: str = "0.0.1"


@dataclass(frozen=True)
class MCPToolCallResult:
    ok: bool
    status: int
    content: list[dict[str, Any]]
    text: str
    raw: dict[str, Any] | None
    error: dict[str, Any] | None
    duration_ms: int


class MCPClient:
    """General-purpose MCP client (protocol/lifecycle + tools/call).

    This client is *mechanical*:
      - It does NOT know OpenMemory tool semantics.
      - It does NOT inject user_id.
      - It does NOT interpret 'score' or salience.
      - It only normalizes MCP JSON-RPC responses into a stable structure.
    """

    def __init__(
        self,
        *,
        servers: dict[str, MCPServerConfig],
        timeout_s: float = 10.0,
    ):
        self._servers = servers
        self._transport = StreamableHttpTransport(timeout_s=timeout_s)

        # Per-server readiness state.
        self._ready: set[str] = set()
        self._session_id: dict[str, str] = {}

        # tools/list cache: server_id -> list[tool spec dict]
        self._tools_cache: dict[str, list[dict[str, Any]]] = {}

    def has_server(self, server_id: str) -> bool:
        return server_id in self._servers

    def ensure_ready(self, server_id: str) -> None:
        if server_id in self._ready:
            return
        cfg = self._get_cfg(server_id)

        # initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": cfg.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": cfg.client_name, "version": cfg.client_version},
            },
        }
        init_resp = self._post(server_id, init_payload)
        if not init_resp.ok:
            raise RuntimeError(
                f"mcp.initialize failed: server={server_id} status={init_resp.status} "
                f"error={init_resp.error}"
            )

        # Some servers may return Mcp-Session-Id. OpenMemory does not (in your probe),
        # but we support it generically.
        sid = init_resp.raw_headers.get("Mcp-Session-Id") if init_resp.raw_headers else None
        if sid:
            self._session_id[server_id] = sid

        # initialized notification (no id)
        initialized_payload = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        _ = self._post(server_id, initialized_payload, allow_empty_body=True)

        self._ready.add(server_id)

    def list_tools(self, server_id: str, *, refresh: bool = False) -> list[dict[str, Any]]:
        self.ensure_ready(server_id)
        if (not refresh) and server_id in self._tools_cache:
            return list(self._tools_cache[server_id])

        payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = self._post(server_id, payload)
        if not resp.ok:
            raise RuntimeError(
                f"mcp.tools/list failed: server={server_id} status={resp.status} "
                f"error={resp.error}"
            )

        tools = []
        raw = resp.raw or {}
        try:
            tools = (raw.get("result") or {}).get("tools") or []
        except Exception:
            tools = []

        if not isinstance(tools, list):
            tools = []

        self._tools_cache[server_id] = tools
        return list(tools)

    def call_tool(
        self,
        server_id: str,
        *,
        name: str,
        arguments: dict[str, Any],
        request_id: int = 10,
    ) -> MCPToolCallResult:
        self.ensure_ready(server_id)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        resp = self._post(server_id, payload)
        if not resp.ok:
            return MCPToolCallResult(
                ok=False,
                status=resp.status,
                content=[],
                text="",
                raw=resp.raw,
                error=resp.error or {"message": "tools/call failed"},
                duration_ms=resp.duration_ms,
            )

        raw = resp.raw or {}
        result = raw.get("result") or {}
        content = result.get("content") or []
        if not isinstance(content, list):
            content = []

        # Concatenate text blocks for convenience
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        text = "\n".join(parts).strip()

        return MCPToolCallResult(
            ok=True,
            status=resp.status,
            content=content,
            text=text,
            raw=raw,
            error=None,
            duration_ms=resp.duration_ms,
        )

    # -----------------
    # Internals
    # -----------------

    def _get_cfg(self, server_id: str) -> MCPServerConfig:
        cfg = self._servers.get(server_id)
        if cfg is None:
            raise KeyError(f"unknown MCP server_id: {server_id}")
        if not cfg.url:
            raise ValueError(f"MCP server '{server_id}' has empty url")
        return cfg

    @dataclass(frozen=True)
    class _PostResult:
        ok: bool
        status: int
        raw: dict[str, Any] | None
        error: dict[str, Any] | None
        duration_ms: int
        raw_headers: dict[str, str] | None = None

    def _post(
        self,
        server_id: str,
        payload: dict[str, Any],
        *,
        allow_empty_body: bool = False,
    ) -> _PostResult:
        cfg = self._get_cfg(server_id)

        headers = dict(cfg.headers or {})
        headers["MCP-Protocol-Version"] = cfg.protocol_version

        sid = self._session_id.get(server_id)
        if sid:
            headers["Mcp-Session-Id"] = sid

        t0 = time.time()
        http = self._transport.post_jsonrpc(url=cfg.url, headers=headers, payload=payload)
        dt_ms = int((time.time() - t0) * 1000)

        if allow_empty_body and not http.body_text.strip():
            return self._PostResult(
                ok=True,
                status=http.status,
                raw=None,
                error=None,
                duration_ms=dt_ms,
                raw_headers=http.headers,
            )

        try:
            raw = json.loads(http.body_text)
        except Exception as e:
            if allow_empty_body and http.status in (200, 202):
                return self._PostResult(
                    ok=True,
                    status=http.status,
                    raw=None,
                    error=None,
                    duration_ms=dt_ms,
                    raw_headers=http.headers,
                )
            return self._PostResult(
                ok=False,
                status=http.status,
                raw=None,
                error={"message": "invalid json-rpc response", "detail": str(e)},
                duration_ms=dt_ms,
                raw_headers=http.headers,
            )

        if isinstance(raw, dict) and "error" in raw:
            return self._PostResult(
                ok=False,
                status=http.status,
                raw=raw,
                error=raw.get("error") if isinstance(raw.get("error"), dict) else {"message": str(raw.get("error"))},
                duration_ms=dt_ms,
                raw_headers=http.headers,
            )

        return self._PostResult(
            ok=True,
            status=http.status,
            raw=raw if isinstance(raw, dict) else {"result": raw},
            error=None,
            duration_ms=dt_ms,
            raw_headers=http.headers,
        )