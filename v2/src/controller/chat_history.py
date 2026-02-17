from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
import json


@dataclass(frozen=True)
class ChatTurn:
    role: str          # "human" | "you" (your convention)
    content: str
    ts: str            # ISO8601 string


def append_turn(*, history_file: Path, role: str, content: str, ts: str) -> None:
    """
    Append a single turn to JSONL.
    Does not enforce a max; the UI decides how much to read.
    """
    history_file.parent.mkdir(parents=True, exist_ok=True)
    rec = {"role": role, "content": content, "ts": ts}
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_tail(*, history_file: Path, limit: int) -> List[ChatTurn]:
    """
    Read the last `limit` turns from JSONL.
    Simple implementation: read all and slice. Good enough for now.
    """
    if limit <= 0:
        return []

    if not history_file.exists():
        return []

    lines = history_file.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:]
    out: List[ChatTurn] = []
    for line in tail:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            out.append(
                ChatTurn(
                    role=str(obj.get("role", "") or ""),
                    content=str(obj.get("content", "") or ""),
                    ts=str(obj.get("ts", "") or ""),
                )
            )
        except Exception:
            # Ignore malformed lines (robustness over strictness for now)
            continue
    return out
