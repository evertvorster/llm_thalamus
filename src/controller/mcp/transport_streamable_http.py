from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body_text: str


class StreamableHttpTransport:
    """MCP Streamable HTTP transport (JSON-RPC over POST).

    Notes:
      - We set Accept: application/json, text/event-stream per MCP examples.
      - OpenMemory returns normal JSON in the body for JSON-RPC responses.
      - If a server ever returns SSE, we'd need an SSE parser; out of scope for v1.
    """

    def __init__(self, *, timeout_s: float = 10.0):
        self._timeout_s = timeout_s

    def post_jsonrpc(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> HttpResponse:
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **headers,
            },
        )

        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            status = int(getattr(resp, "status", 0) or 0)
            resp_headers = {k: v for (k, v) in resp.headers.items()}
            body_text = resp.read().decode("utf-8", errors="replace")

        return HttpResponse(status=status, headers=resp_headers, body_text=body_text)