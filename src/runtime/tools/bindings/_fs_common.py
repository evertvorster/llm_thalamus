from __future__ import annotations

from pathlib import Path

from runtime.tools.resources import ToolResources


def working_dir(resources: ToolResources) -> Path:
    base = getattr(resources, "working_dir", None) or Path.cwd()
    return Path(base).expanduser().resolve()


def resolve_path(resources: ToolResources, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("path must be a non-empty string")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = working_dir(resources) / path
    return path.resolve()
