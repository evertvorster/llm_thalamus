from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_thalamus.config.access import get_config
from llm_thalamus.config.paths import resolve_app_path


@dataclass(frozen=True)
class MessageRecord:
    ts: str
    role: str
    content: str

    def as_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts, "role": self.role, "content": self.content}


def _utc_iso(ts: Optional[datetime] = None) -> str:
    dt = ts or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _read_all_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if "role" not in obj or "content" not in obj:
                    continue
                records.append(obj)
    except OSError:
        return []

    return records


def _rewrite_records(path: Path, records: List[Dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
        f.flush()
    tmp.replace(path)


class MessageHistoryStore:
    """
    JSONL on-disk message history.

    Record format (1 JSON object per line):
      {"ts":"2025-12-15T18:13:00Z","role":"human","content":"..."}
    """

    def __init__(self, *, filename: str, max_messages: int) -> None:
        self._filename = filename
        self._max_messages = max(0, int(max_messages))

    @classmethod
    def from_config(cls) -> "MessageHistoryStore":
        cfg = get_config()

        # Keep compatibility with the old config naming:
        # - message_history_max (cap, 0 disables)
        # - message_file (filename within data root)
        max_messages = getattr(cfg, "message_history_max", 100)
        try:
            max_messages = int(max_messages)
        except Exception:
            max_messages = 100

        filename = getattr(cfg, "message_file", None) or "chat_history.jsonl"
        return cls(filename=str(filename), max_messages=max_messages)

    def history_path(self) -> Path:
        """
        Resolve the chat history file in the app-controlled 'data' area.
        """
        p = resolve_app_path(self._filename, kind="data")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def trim_to_cap(self) -> None:
        """
        Enforce on-disk cap immediately.
        If cap <= 0: remove history file best-effort.
        """
        path = self.history_path()
        if self._max_messages <= 0:
            try:
                path.unlink(missing_ok=True)
            except TypeError:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
            return

        records = _read_all_records(path)
        if len(records) > self._max_messages:
            _rewrite_records(path, records[-self._max_messages :])

    def append_message(self, role: str, content: str, *, ts: Optional[datetime] = None) -> None:
        """
        Append one message record, then trim to the configured on-disk cap.
        """
        path = self.history_path()

        if self._max_messages <= 0:
            # History disabled: best effort remove any existing file and exit.
            try:
                path.unlink(missing_ok=True)
            except TypeError:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
            return

        rec = MessageRecord(ts=_utc_iso(ts), role=str(role), content=str(content))

        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.as_dict(), ensure_ascii=False))
            f.write("\n")
            f.flush()

        # Handles cap reductions cleanly.
        records = _read_all_records(path)
        if len(records) > self._max_messages:
            _rewrite_records(path, records[-self._max_messages :])

    def get_last_messages(self, n: int) -> List[Dict[str, Any]]:
        """
        Return up to the last n messages (oldest->newest order).
        """
        try:
            n = int(n)
        except Exception:
            n = 0
        if n <= 0:
            return []

        path = self.history_path()
        records = _read_all_records(path)
        return records[-n:] if records else []

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        msgs = self.get_last_messages(1)
        return msgs[0] if msgs else None

    def get_last_user_message(self) -> Optional[Dict[str, Any]]:
        """
        Return the most recent message whose role is 'user' or 'human'.
        (Thalamus commonly uses 'human' / 'you'.)
        """
        path = self.history_path()
        records = _read_all_records(path)
        for rec in reversed(records):
            role = str(rec.get("role", "")).lower()
            if role in ("user", "human"):
                return rec
        return None

    def format_for_prompt(self, n: int, *, max_chars_per_message: Optional[int] = None) -> str:
        """
        Convenience formatter for your "Conversation history" prompt block.
        """
        msgs = self.get_last_messages(n)
        if not msgs:
            return ""

        lines: List[str] = []
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            if max_chars_per_message is not None and max_chars_per_message > 0:
                content = content[:max_chars_per_message]
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)
