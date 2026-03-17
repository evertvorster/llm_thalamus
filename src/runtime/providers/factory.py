from __future__ import annotations

from typing import Optional

from .base import LLMProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


def make_provider(
    name: str,
    *,
    kind: str,
    base_url: Optional[str] = None,
    api_key: str | None = None,
) -> LLMProvider:
    name = (name or "").strip().lower()
    kind = (kind or name).strip().lower()
    if kind == "ollama":
        return OllamaProvider(base_url=base_url)
    if kind in {"openai_compatible", "openai"}:
        return OpenAICompatibleProvider(
            provider_name=name or kind,
            base_url=str(base_url or ""),
            api_key=api_key,
        )
    raise ValueError(f"Unknown provider kind: {kind}")
