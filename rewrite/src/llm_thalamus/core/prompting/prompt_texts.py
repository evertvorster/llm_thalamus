from __future__ import annotations

from pathlib import Path
from typing import Optional

from llm_thalamus.config.paths import resources_root


def load_prompt_text(call_name: str) -> str:
    """Load a prompt template from resources/config.

    Naming convention: resources/config/prompt_<call_name>.txt
    Example: call_name="answer" -> prompt_answer.txt
    """
    p = resources_root() / "config" / f"prompt_{call_name}.txt"
    if not p.exists():
        raise FileNotFoundError(f"Prompt template not found: {p}")
    return p.read_text(encoding="utf-8")
