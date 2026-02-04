from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


def _post_json(url: str, payload: dict, *, timeout_s: float = 120.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response: {e}") from e


def ollama_generate(
    *,
    ollama_url: str,
    model: str,
    prompt: str,
    timeout_s: float = 120.0,
) -> str:
    base = ollama_url.rstrip("/")
    endpoint = f"{base}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    out = _post_json(endpoint, payload, timeout_s=timeout_s)

    # Ollama commonly returns {"response": "...", ...} or {"error": "..."}
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(str(out["error"]))

    resp = out.get("response", "")
    return str(resp)


def run_ollama_interactive_chat(
    *,
    ollama_url: str,
    model: str,
    timeout_s: float = 120.0,
) -> int:
    print("\n== Ollama interactive chat (no history) ==")
    print(f"ollama_url: {ollama_url}")
    print(f"model:      {model}")
    print("Exit with empty line, Ctrl-D, Ctrl-C, ':q', 'quit', or 'exit'.\n")

    while True:
        try:
            s = input("> ").strip()
        except EOFError:
            print("\nEOF -> exiting test.")
            return 0
        except KeyboardInterrupt:
            print("\n^C -> exiting test.")
            return 0

        if s == "" or s.lower() in {":q", "quit", "exit"}:
            print("Exiting test.")
            return 0

        try:
            reply = ollama_generate(
                ollama_url=ollama_url,
                model=model,
                prompt=s,
                timeout_s=timeout_s,
            )
        except Exception as e:
            print(f"[ERROR] ollama call failed: {type(e).__name__}: {e}")
            return 1

        # Keep output clean and direct
        print(reply.strip())
        print("")
