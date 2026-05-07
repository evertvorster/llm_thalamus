from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StdioResponse:
    status: int
    headers: dict[str, str]
    body_text: str


@dataclass(frozen=True)
class StdioServerProcess:
    process: subprocess.Popen[str]
    lock: threading.Lock


class StdioTransport:
    """Line-delimited JSON-RPC over a subprocess stdin/stdout.

    This is sufficient for stdio MCP servers such as ``python -m mempalace.mcp_server``
    that read one JSON object per line and write one JSON response per line.
    """

    def __init__(self, *, timeout_s: float = 10.0):
        self._timeout_s = timeout_s
        self._processes: dict[str, StdioServerProcess] = {}

    def post_jsonrpc(
        self,
        *,
        server_id: str,
        command: str,
        args: list[str],
        cwd: str | None,
        env: dict[str, str] | None,
        payload: dict[str, Any],
        expect_response: bool = True,
    ) -> StdioResponse:
        proc = self._ensure_process(server_id=server_id, command=command, args=args, cwd=cwd, env=env)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with proc.lock:
            if proc.process.stdin is None or proc.process.stdout is None:
                raise RuntimeError(f"stdio MCP server '{server_id}' has closed pipes")
            proc.process.stdin.write(line)
            proc.process.stdin.flush()
            if not expect_response:
                return StdioResponse(status=202, headers={}, body_text="")
            body = self._readline_with_timeout(proc.process, server_id=server_id)
        return StdioResponse(status=200, headers={}, body_text=body)

    def close(self) -> None:
        for wrapped in list(self._processes.values()):
            proc = wrapped.process
            if proc.poll() is not None:
                continue
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()

    def _ensure_process(
        self,
        *,
        server_id: str,
        command: str,
        args: list[str],
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> StdioServerProcess:
        existing = self._processes.get(server_id)
        if existing is not None and existing.process.poll() is None:
            return existing

        process = subprocess.Popen(
            [command, *args],
            cwd=cwd or None,
            env={**os.environ, **dict(env or {})},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        wrapped = StdioServerProcess(process=process, lock=threading.Lock())
        self._processes[server_id] = wrapped
        return wrapped

    def _readline_with_timeout(self, process: subprocess.Popen[str], *, server_id: str) -> str:
        if process.stdout is None:
            raise RuntimeError(f"stdio MCP server '{server_id}' stdout is closed")

        result: dict[str, str] = {}
        error: dict[str, BaseException] = {}

        def _read() -> None:
            try:
                result["line"] = process.stdout.readline()
            except BaseException as e:  # pragma: no cover - defensive thread boundary
                error["error"] = e

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(self._timeout_s)
        if t.is_alive():
            raise TimeoutError(f"stdio MCP server '{server_id}' did not respond within {self._timeout_s:g}s")
        if "error" in error:
            raise RuntimeError(f"stdio MCP server '{server_id}' read failed: {error['error']}")
        line = result.get("line", "")
        if line == "":
            stderr = ""
            try:
                if process.stderr is not None:
                    stderr = process.stderr.read() or ""
            except Exception:
                pass
            raise RuntimeError(f"stdio MCP server '{server_id}' exited without response: {stderr[-1000:]}")
        return line
