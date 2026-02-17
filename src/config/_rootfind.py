from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path) -> Path:
    """
    Find repo/project root by walking upwards until we find:
      resources/config/config.json

    This keeps llm_thalamus.py layout-agnostic.
    """
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "resources" / "config" / "config.json").exists():
            return parent
    return start.resolve()
