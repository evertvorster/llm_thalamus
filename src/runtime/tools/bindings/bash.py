from __future__ import annotations

import subprocess

from runtime.tools.bindings._fs_common import working_dir
from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult

_MAX_OUTPUT_CHARS = 50_000


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text, False
    return text[-_MAX_OUTPUT_CHARS:], True


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("bash: args must be an object")
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("bash: command must be a non-empty string")
        timeout = int(args.get("timeout") or 60)
        timeout = max(1, min(timeout, 600))
        cwd = working_dir(resources)
        try:
            proc = subprocess.run(
                ["bash", "-lc", command],
                cwd=str(cwd),
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            stdout, stdout_truncated = _truncate(proc.stdout or "")
            stderr, stderr_truncated = _truncate(proc.stderr or "")
            return {
                "ok": proc.returncode == 0,
                "command": command,
                "cwd": str(cwd),
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            }
        except subprocess.TimeoutExpired as e:
            stdout, stdout_truncated = _truncate(e.stdout or "")
            stderr, stderr_truncated = _truncate(e.stderr or "")
            return {
                "ok": False,
                "command": command,
                "cwd": str(cwd),
                "returncode": None,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "error": f"command timed out after {timeout}s",
            }

    return handler
