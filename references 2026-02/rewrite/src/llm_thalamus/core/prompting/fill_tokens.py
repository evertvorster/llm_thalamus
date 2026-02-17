from __future__ import annotations

from typing import Mapping


def fill_template(template: str, tokens: Mapping[str, str]) -> str:
    """
    Deterministically fill a prompt template using __TOKEN__ placeholders.

    Example:
      template: "Hello __NAME__"
      tokens: {"NAME": "Evert"}
      -> "Hello Evert"

    Single responsibility: pure string replacement (no I/O).
    """
    out = template

    # Stable order to keep behavior deterministic (useful for debugging).
    for key in sorted(tokens.keys()):
        value = tokens[key]
        out = out.replace(f"__{key}__", str(value))

    return out


# Back-compat aliases (in case other migrated code used a different function name)
def fill_tokens(template: str, tokens: Mapping[str, str]) -> str:
    return fill_template(template, tokens)


def apply_tokens(template: str, tokens: Mapping[str, str]) -> str:
    return fill_template(template, tokens)
