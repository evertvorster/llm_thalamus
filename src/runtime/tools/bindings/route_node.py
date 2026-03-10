from __future__ import annotations

from typing import Any

from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


ALLOWED_STATUS = {"complete", "incomplete", "blocked"}


def bind(resources: ToolResources) -> ToolHandler:
    _ = resources

    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("route_node: args must be an object")

        node = str(args.get("node") or "").strip().lower()
        if not node:
            raise ValueError("route_node: 'node' must be a non-empty string")

        status = str(args.get("status") or "").strip().lower()
        if status not in ALLOWED_STATUS:
            raise ValueError("route_node: 'status' must be one of complete|incomplete|blocked")

        raw_issues = args.get("issues")
        issues: list[str] = []
        if raw_issues is not None:
            if not isinstance(raw_issues, list):
                raise ValueError("route_node: 'issues' must be an array of strings")
            for issue in raw_issues:
                s = str(issue).strip()
                if s:
                    issues.append(s)

        handoff_note = args.get("handoff_note")
        if handoff_note is None:
            handoff_note_text = ""
        elif isinstance(handoff_note, str):
            handoff_note_text = handoff_note.strip()
        else:
            raise ValueError("route_node: 'handoff_note' must be a string")

        return {
            "ok": True,
            "node": node,
            "status": status,
            "issues": issues,
            "handoff_note": handoff_note_text,
        }

    return handler
