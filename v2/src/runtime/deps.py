from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol


class LLMClient(Protocol):
    """
    Minimal LLM interface for bootstrap.

    - complete_text: free-form assistant text (answer node)
    - complete_json: MUST return JSON text only (router node)
    - emit_thought: optional callback for streaming thinking chunks
    """
    def complete_text(self, prompt: str, *, emit_thought: Optional[Callable[[str], None]] = None) -> str: ...
    def complete_json(self, prompt: str, *, emit_thought: Optional[Callable[[str], None]] = None) -> str: ...


@dataclass(frozen=True)
class Deps:
    llm: LLMClient
    prompt_root: str  # e.g. "runtime/prompts"
