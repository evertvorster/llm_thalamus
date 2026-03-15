from __future__ import annotations

from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


def bind(resources: ToolResources) -> ToolHandler:
    _ = resources

    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("reflect_complete: args must be an object")

        topics = args.get("topics")
        if not isinstance(topics, list):
            raise ValueError("reflect_complete: 'topics' must be an array of strings")
        out_topics: list[str] = []
        for topic in topics:
            s = str(topic).strip()
            if s:
                out_topics.append(s)

        stored = args.get("stored")
        if not isinstance(stored, list):
            raise ValueError("reflect_complete: 'stored' must be an array")

        stored_count_raw = args.get("stored_count")
        if not isinstance(stored_count_raw, (int, float)) or isinstance(stored_count_raw, bool):
            raise ValueError("reflect_complete: 'stored_count' must be a number")
        stored_count = int(stored_count_raw)
        if stored_count < 0:
            stored_count = 0

        issues_raw = args.get("issues")
        issues: list[str] = []
        if issues_raw is not None:
            if not isinstance(issues_raw, list):
                raise ValueError("reflect_complete: 'issues' must be an array of strings")
            for issue in issues_raw:
                s = str(issue).strip()
                if s:
                    issues.append(s)

        notes_raw = args.get("notes")
        if notes_raw is None:
            notes = ""
        elif isinstance(notes_raw, str):
            notes = notes_raw.strip()
        else:
            raise ValueError("reflect_complete: 'notes' must be a string")

        return {
            "ok": True,
            "topics": out_topics,
            "stored": stored,
            "stored_count": stored_count,
            "issues": issues,
            "notes": notes,
        }

    return handler
