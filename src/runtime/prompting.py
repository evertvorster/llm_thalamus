from __future__ import annotations

import re
from typing import Mapping


_TOKEN_RE = re.compile(r"<<([A-Z0-9_]+)>>")


def render_tokens(template: str, mapping: Mapping[str, str]) -> str:
    template_tokens = _TOKEN_RE.findall(template)
    leftover = [f"<<{token_name}>>" for token_name in template_tokens if token_name not in mapping]
    if leftover:
        raise RuntimeError(f"Unresolved prompt tokens: {sorted(set(leftover))}")

    def _replace(match: re.Match[str]) -> str:
        token_name = match.group(1)
        return mapping[token_name]

    return _TOKEN_RE.sub(_replace, template)
