from __future__ import annotations

from pathlib import Path


def load_prompt_text(prompt_root: str, rel_path: str) -> str:
    p = Path(prompt_root) / rel_path
    return p.read_text(encoding="utf-8")
