from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from paths import get_user_config_path, resolve_app_path

# JSONL record format:
# {"ts":"2025-12-15T18:13:00Z","role":"human","content":"..."}
# {"ts":"2025-12-15T18:13:05Z","role":"you","content":"..."}

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """
    Load and cache the current config.json using the canonical resolver in paths.py.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        cfg_path = get_user_config_path()
        with cfg_path.open("r", encoding="utf-8") as f:
            _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE


def refresh_config_cache() -> None:
    """Force reload of config on next access (useful if UI edits config live)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


def _get_thalamus_setting(key: str, default: Any) -> Any:
    cfg = _load_config()
    th = cfg.get("thalamus", {}) if isinstance(cfg, dict) else {}
    v = th.get(key, default)
    return default if v is None else v


def _max_history() -> int:
    """
    How many turns we store on disk (rolling cap).
    If set <= 0, history is treated as disabled (file removed on trim/append).
    """
    try:
        v = int(_get_thalamus_setting("message_history", 100))
        return max(v, 0)
    except Exception:
        return 100


def _history_path() -> Path:
    """
    Resolve the chat history file in the same app-controlled 'data' area as the DB.
    message_file is treated as a filename or relative path.
    """
    name = str(_get_thalamus_setting("message_file", "chat_history.jsonl"))
    p = resolve_app_path(name, kind="data")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


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


def trim_to_config() -> None:
    """
    Enforce thalamus.message_history on disk immediately.

    Useful if you want the system to react to a reduction without waiting for the
    next appended message.
    """
    path = _history_path()
    max_keep = _max_history()

    if max_keep <= 0:
        try:
            path.unlink(missing_ok=True)  # py3.8+
        except TypeError:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        return

    records = _read_all_records(path)
    if len(records) > max_keep:
        _rewrite_records(path, records[-max_keep:])


def append_message(role: str, content: str, *, ts: Optional[datetime] = None) -> None:
    """
    Append one message record, then trim to the configured on-disk cap.
    """
    max_keep = _max_history()
    path = _history_path()

    if max_keep <= 0:
        # History disabled: best effort remove any existing file and exit.
        try:
            path.unlink(missing_ok=True)  # py3.8+
        except TypeError:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        return

    rec = {
        "ts": _utc_iso(ts),
        "role": str(role),
        "content": str(content),
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False))
        f.write("\n")
        f.flush()

    # Enforce the storage cap (handles reductions cleanly).
    records = _read_all_records(path)
    if len(records) > max_keep:
        _rewrite_records(path, records[-max_keep:])


def get_last_messages(n: int) -> List[Dict[str, Any]]:
    """
    Return up to the last n messages (oldest->newest order).
    n is per-call and must be provided by the caller.
    """
    try:
        n = int(n)
    except Exception:
        n = 0
    if n <= 0:
        return []

    path = _history_path()
    records = _read_all_records(path)
    if not records:
        return []

    return records[-n:]


def get_last_message() -> Optional[Dict[str, Any]]:
    msgs = get_last_messages(1)
    return msgs[0] if msgs else None


def get_last_user_message() -> Optional[Dict[str, Any]]:
    """
    Return the most recent message whose role is 'user' or 'human'.
    (Thalamus commonly uses 'human' / 'you'.)
    """
    path = _history_path()
    records = _read_all_records(path)
    for rec in reversed(records):
        role = str(rec.get("role", "")).lower()
        if role in ("user", "human"):
            return rec
    return None


def format_for_prompt(n: int, *, max_chars_per_message: Optional[int] = None) -> str:
    """
    Convenience formatter for your "Conversation history" prompt block.
    """
    msgs = get_last_messages(n)
    if not msgs:
        return ""

    lines: List[str] = []
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if max_chars_per_message is not None and max_chars_per_message > 0:
            content = content[:max_chars_per_message]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
