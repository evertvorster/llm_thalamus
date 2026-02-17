from __future__ import annotations

import re
from typing import Mapping


_TOKEN_RE = re.compile(r"<<[A-Z0-9_]+>>")


def render_tokens(template: str, mapping: Mapping[str, str]) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace(f"<<{k}>>", v)

    leftover = _TOKEN_RE.findall(out)
    if leftover:
        raise RuntimeError(f"Unresolved prompt tokens: {sorted(set(leftover))}")
    return out
