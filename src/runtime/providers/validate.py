from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .base import LLMProvider, ProviderError
from .types import ModelInfo


@dataclass(frozen=True)
class RequiredModel:
    role: str
    model: str
    requires: Sequence[str]  # e.g. ["json_mode", "tools"]


def validate_models_installed(
    provider: LLMProvider,
    required: Sequence[RequiredModel],
) -> None:
    models = provider.list_models()
    installed = {m.name for m in models}

    missing: List[str] = []
    for r in required:
        if r.model not in installed:
            missing.append(f"{r.role}: {r.model}")

    if missing:
        raise ProviderError(
            "Missing required models:\n  " + "\n  ".join(missing)
        )

    # Capability validation can be strict once you add probes that fill ModelInfo.capabilities.
