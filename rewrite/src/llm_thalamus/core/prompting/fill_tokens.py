from __future__ import annotations

from typing import Mapping


def fill_tokens(template: str, tokens: Mapping[str, str]) -> str:
    """Replace __TOKEN__ placeholders with provided values.

    This is intentionally a dumb, deterministic replacement (legacy-compatible).
    Unknown placeholders are left as-is.
    """
    out = template
    for k, v in tokens.items():
        out = out.replace(f"__{k}__", v)
    return out
