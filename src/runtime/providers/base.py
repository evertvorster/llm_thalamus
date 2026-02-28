from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Sequence

from .types import (
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    StreamEvent,
)


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    """
    Provider abstraction for local/remote inference backends.
    All higher layers speak *only* this interface.

    Contract:
    - chat_stream() yields StreamEvent and MUST end with a 'done' event (or 'error').
    - chat() returns a final ChatResponse (non-stream convenience).
    - list_models() returns ModelInfo with capabilities if available.
    - embed() returns embedding vectors in the same order as inputs.
    """

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        raise NotImplementedError

    @abstractmethod
    def chat_stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        raise NotImplementedError

    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    @abstractmethod
    def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError

    # Optional: for health checks / startup validation
    def ping(self) -> None:
        return

    # Optional: expose raw provider metadata (for diagnostics UI)
    def diagnostics(self) -> Dict[str, str]:
        return {}

    # Optional: provider-level capability declaration for startup validation
    def capabilities(self) -> Sequence[str]:
        """Return provider-level supported capabilities.

        Values must be drawn from runtime.providers.types.Capability.
        """
        return []
