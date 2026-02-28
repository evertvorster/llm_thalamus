from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

Role = Literal["human", "you"]


@dataclass(frozen=True)
class ChatTurn:
    ts: str
    role: Role
    content: str


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_history_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def _parse_line(line: str) -> ChatTurn | None:
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("role") not in ("human", "you"):
        return None
    if not isinstance(obj.get("content"), str):
        return None
    if not isinstance(obj.get("ts"), str):
        return None
    return ChatTurn(obj["ts"], obj["role"], obj["content"])


def read_tail(*, history_file: Path, limit: int) -> list[ChatTurn]:
    if limit <= 0 or not history_file.exists():
        return []

    buf: deque[ChatTurn] = deque(maxlen=limit)
    with history_file.open("r", encoding="utf-8") as f:
        for line in f:
            turn = _parse_line(line)
            if turn:
                buf.append(turn)
    return list(buf)


def trim_to_max(*, history_file: Path, max_turns: int) -> None:
    if max_turns <= 0:
        try:
            history_file.unlink()
        except FileNotFoundError:
            pass
        return

    turns = read_tail(history_file=history_file, limit=max_turns)
    tmp = history_file.with_suffix(history_file.suffix + ".tmp")

    with tmp.open("w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t.__dict__, ensure_ascii=False) + "\n")

    os.replace(tmp, history_file)


def append_turn(
    *,
    history_file: Path,
    role: Role,
    content: str,
    max_turns: int,
    ts: str | None = None,
) -> None:
    if max_turns <= 0:
        trim_to_max(history_file=history_file, max_turns=max_turns)
        return

    ensure_history_file(history_file)

    record = {
        "ts": ts or now_iso_utc(),
        "role": role,
        "content": content,
    }

    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    trim_to_max(history_file=history_file, max_turns=max_turns)


def format_for_prompt(turns: Iterable[ChatTurn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in turns)
