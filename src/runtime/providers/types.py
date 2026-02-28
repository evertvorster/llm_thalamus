from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional, Sequence, Union


Role = Literal["system", "developer", "user", "assistant", "tool"]
EventType = Literal[
    "delta_text",
    "delta_thinking",
    "tool_call",
    "tool_result",
    "usage",
    "error",
    "done",
]


@dataclass(frozen=True)
class ToolDef:
    """
    OpenAI-style tool definition. Providers may down-convert if they support a subset.
    """
    name: str
    description: str
    # JSON Schema for arguments
    parameters: Dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """
    Canonical tool call emitted by model/provider.
    """
    id: str
    name: str
    arguments_json: str  # raw JSON string (do not parse here)


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    name: Optional[str] = None
    # For tool messages: associate with tool_call_id
    tool_call_id: Optional[str] = None


@dataclass(frozen=True)
class Usage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass(frozen=True)
class StreamEvent:
    type: EventType
    text: Optional[str] = None               # for delta_text / delta_thinking
    tool_call: Optional[ToolCall] = None     # for tool_call
    usage: Optional[Usage] = None            # for usage
    error: Optional[str] = None              # for error


@dataclass(frozen=True)
class ChatParams:
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    seed: Optional[int] = None
    num_ctx: Optional[int] = None

    stop: Optional[List[str]] = None

    # Provider specific escape hatch (kept explicit so callers know when they’re relying on it)
    extra: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: Sequence[Message]

    tools: Optional[Sequence[ToolDef]] = None
    # "json" or JSON Schema dict
    response_format: Optional[Union[Literal["json"], Dict[str, Any]]] = None

    params: Optional[ChatParams] = None
    stream: bool = True


@dataclass(frozen=True)
class ChatResponse:
    """
    Non-stream (final) response form.
    """
    message: Message
    tool_calls: Optional[List[ToolCall]] = None
    usage: Optional[Usage] = None


@dataclass(frozen=True)
class EmbeddingRequest:
    model: str
    texts: Sequence[str]


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: List[List[float]]


Capability = Literal["chat", "embeddings", "tools", "json_mode", "vision", "fim", "streaming"]


@dataclass(frozen=True)
class ModelInfo:
    name: str
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    context_length: Optional[int] = None
    capabilities: Optional[List[Capability]] = None
