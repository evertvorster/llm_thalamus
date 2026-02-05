from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Literal

import requests


ChunkKind = Literal["thinking", "response"]
Chunk = tuple[ChunkKind, str]


def ollama_generate_stream(
    *,
    llm_url: str,
    model: str,
    prompt: str,
    timeout_connect_s: float = 10.0,
    timeout_read_s: float = 300.0,
) -> Iterator[Chunk]:
    """
    Yield tagged streaming chunks from Ollama /api/generate.

    - ("thinking", <text>) for model internal reasoning (if present)
    - ("response", <text>) for user-facing output tokens
    """
    url = llm_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }

    r = requests.post(url, json=payload, timeout=(timeout_connect_s, timeout_read_s), stream=True)
    r.raise_for_status()

    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue

        try:
            data = json.loads(line)
        except Exception as e:
            raise RuntimeError(f"Malformed Ollama stream line: {line!r}") from e

        if data.get("error"):
            raise RuntimeError(str(data.get("error")))

        thinking_tok = data.get("thinking")
        if thinking_tok:
            t = str(thinking_tok)
            if t:
                yield ("thinking", t)

        resp_tok = data.get("response")
        if resp_tok:
            t = str(resp_tok)
            if t:
                yield ("response", t)

        if data.get("done") is True:
            break
