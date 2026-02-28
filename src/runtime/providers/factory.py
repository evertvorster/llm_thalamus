from __future__ import annotations

from typing import Optional

from .base import LLMProvider
from .ollama import OllamaProvider


def make_provider(name: str, base_url: Optional[str] = None) -> LLMProvider:
    name = (name or "").strip().lower()
    if name == "ollama":
        return OllamaProvider(base_url=base_url)
    raise ValueError(f"Unknown provider: {name}")
