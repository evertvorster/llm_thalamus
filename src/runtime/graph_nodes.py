from __future__ import annotations

from collections.abc import Iterator

from orchestrator.events import Event
from orchestrator.transport_ollama import Chunk


def emit_node_start(node: str) -> Event:
    return {"type": "node_start", "node": node}


def emit_node_end(node: str) -> Event:
    return {"type": "node_end", "node": node}


def emit_log(text: str) -> Event:
    return {"type": "log", "text": text}


def emit_final(answer: str) -> Event:
    return {"type": "final", "answer": answer}


def collect_streamed_response(
    stream: Iterator[Chunk],
    *,
    on_chunk: callable,
) -> str:
    """
    Mirrors your current behavior:
    - emit every chunk (thinking+response) as log text
    - only concatenate response chunks into final response body
    Transport yields ("thinking"|"response", text). :contentReference[oaicite:5]{index=5}
    """
    parts: list[str] = []
    for kind, text in stream:
        if text:
            on_chunk(text)
        if kind == "response" and text:
            parts.append(text)
    return "".join(parts)
