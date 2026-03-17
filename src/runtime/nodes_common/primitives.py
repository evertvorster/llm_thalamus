from __future__ import annotations

import json
import re
from typing import Any

from runtime.emitter import TurnEmitter
from runtime.json_extract import extract_first_json_object


def get_emitter(state: dict) -> TurnEmitter:
    em = (state.get("runtime") or {}).get("emitter")
    if em is None:
        raise RuntimeError("runtime.emitter missing from state (runner must install TurnEmitter)")
    return em  # type: ignore[return-value]


def append_node_trace(state: dict, node_id: str) -> None:
    rt = state.setdefault("runtime", {})
    trace = rt.setdefault("node_trace", [])
    if isinstance(trace, list):
        trace.append(node_id)


def bump_counter(state: dict, key: str) -> int:
    rt = state.setdefault("runtime", {})
    try:
        rt[key] = int(rt.get(key) or 0) + 1
    except Exception:
        rt[key] = 1
    return int(rt[key])


def stable_json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def parse_first_json_object(text: str) -> dict:
    try:
        return extract_first_json_object(text)
    except Exception as e:
        raise RuntimeError("output must be a JSON object") from e


def normalize_completion_sentinel(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).upper()
