from __future__ import annotations

import json
from collections.abc import Iterator

import requests


def ollama_generate_stream(
    *,
    llm_url: str,
    model: str,
    prompt: str,
    timeout_connect_s: float = 10.0,
    timeout_read_s: float = 300.0,
) -> Iterator[str]:
    """
    Yield streaming text chunks from Ollama /api/generate.

    We yield both:
      - "thinking" chunks (if present)
      - "response" chunks (normal tokens)

    The caller decides how to present these to UI/logs.
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
            yield str(thinking_tok)

        resp_tok = data.get("response")
        if resp_tok:
            yield str(resp_tok)

        if data.get("done") is True:
            break
