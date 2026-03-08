from __future__ import annotations

import json
import re


_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", flags=re.IGNORECASE)


def _sanitize_candidate(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    s = _CODE_FENCE_RE.sub("", s)
    s = _TRAILING_COMMA_RE.sub(r"\1", s)
    return s.strip()


def extract_first_json_object(text: str) -> dict:
    """Extract the first {...} JSON object from a possibly noisy LLM response.

    The extractor tolerates common LLM formatting issues such as markdown code
    fences and trailing commas before closing braces/brackets.
    """
    s = _sanitize_candidate(text)
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
                candidate = _sanitize_candidate(s[start : i + 1])
                obj = json.loads(candidate)
                if not isinstance(obj, dict):
                    raise ValueError("JSON root is not an object")
                return obj

    raise ValueError("unterminated JSON object")
