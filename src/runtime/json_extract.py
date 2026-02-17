from __future__ import annotations

import json


def extract_first_json_object(text: str) -> dict:
    """
    Extract the first {...} JSON object from a possibly noisy LLM response.
    This mirrors the defensive style you already use in the orchestrator. :contentReference[oaicite:3]{index=3}
    """
    s = text.strip()
    if not s:
        raise ValueError("empty response")

    # Fast path: pure JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Slow path: scan for a balanced {...} region
    start = s.find("{")
    if start < 0:
        raise ValueError("no '{' found")

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start : i + 1]
                obj = json.loads(candidate)
                if not isinstance(obj, dict):
                    raise ValueError("JSON root is not an object")
                return obj

    raise ValueError("unterminated JSON object")
