from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_internal_tools_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"internal_tools.json not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return normalize_internal_tools_config(raw)
def normalize_internal_tools_config(raw: dict[str, Any]) -> dict[str, Any]:
    tools = raw.get("tools", {}) if isinstance(raw, dict) else {}
    if not isinstance(tools, dict):
        raise ValueError("internal_tools.json: tools must be an object")

    normalized_tools: dict[str, Any] = {}
    for tool_name, tool_cfg in tools.items():
        if not isinstance(tool_name, str) or not isinstance(tool_cfg, dict):
            continue
        approval = str(tool_cfg.get("approval") or "auto").strip() or "auto"
        if approval not in {"auto", "ask", "deny"}:
            approval = "auto"
        normalized_tools[tool_name] = {"approval": approval}

    return {"tools": normalized_tools}
