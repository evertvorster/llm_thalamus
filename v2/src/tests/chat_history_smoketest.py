from __future__ import annotations

from pathlib import Path
from typing import Any

from chat_history.message_history import (
    append_turn,
    ensure_history_file,
    read_tail,
)


def run_chat_history_smoketest(*, history_file: Path, max_turns: int) -> None:
    ensure_history_file(history_file)

    append_turn(
        history_file=history_file,
        role="human",
        content="[smoketest] hello from chat history",
        max_turns=max_turns,
    )

    turns = read_tail(history_file, limit=3)
    print(f"history_file: {history_file}")
    print(f"turns_read: {len(turns)}")
    for t in turns:
        print(f"{t.ts} {t.role}: {t.content}")


def _show_one_turn(t: Any, idx: int) -> None:
    print(f"\n--- turn[{idx}] ---")
    print(f"type: {type(t)}")
    # safest introspection across dataclass / attrs / plain objects
    try:
        d = vars(t)
    except Exception:
        d = None
    if isinstance(d, dict):
        print("vars(t):")
        for k in sorted(d.keys()):
            v = d[k]
            s = repr(v)
            if len(s) > 200:
                s = s[:200] + "…"
            print(f"  {k}: {s}")
    else:
        print("vars(t): (unavailable)")

    # Explicit fields the UI/node currently expects
    for k in ("ts", "role", "content", "text", "message"):
        v = getattr(t, k, None)
        s = repr(v)
        if len(s) > 200:
            s = s[:200] + "…"
        print(f"getattr(t, {k!r}): {s}")


def run_chat_messages_format_probe(*, history_file: Path, limit: int = 20) -> None:
    """
    Read the real history file and print the *exact* shape returned by read_tail().

    This is designed to answer one question:
      - Do turns have `.content` (as chat_messages_node expects),
        or something else (e.g. `.text`)?
    """
    ensure_history_file(history_file)

    print("== chat_messages_format_probe ==")
    print(f"history_file: {history_file}")
    try:
        size = history_file.stat().st_size
    except Exception:
        size = None
    print(f"file_size: {size}")

    turns = read_tail(history_file, limit=limit)

    print(f"\nread_tail(limit={limit}) -> type={type(turns)} len={len(turns)}")
    if not turns:
        print("NO TURNS RETURNED")
        return

    # Show the first few turns with rich introspection
    for i, t in enumerate(turns[:10]):
        _show_one_turn(t, i)

    # Also print a “renderer-like” view similar to chat_messages_node
    print("\n== renderer_like ==")
    for t in turns[:10]:
        role = getattr(t, "role", "") or ""
        ts = getattr(t, "ts", "") or ""
        content = getattr(t, "content", None)
        if not content:
            content = getattr(t, "text", None)
        if content is None:
            content = ""
        content = str(content).strip()
        if not content:
            continue
        if ts:
            print(f"{role} ({ts}): {content}")
        else:
            print(f"{role}: {content}")
