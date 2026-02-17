from __future__ import annotations

from llm_thalamus.core.state.message_history import MessageHistoryStore


def main() -> int:
    store = MessageHistoryStore.from_config()
    path = store.history_path()

    if not path.exists():
        raise FileNotFoundError(
            f"Chat history file does not exist at expected path: {path}"
        )

    records = store.get_last_messages(10)
    last = store.get_last_message()
    formatted = store.format_for_prompt(5, max_chars_per_message=120)

    print("probe_message_history: OK")
    print(f"  path={path}")
    print(f"  records_read={len(records)}")
    print(f"  last_role={last.get('role') if last else None}")
    print(f"  formatted_head={formatted[:80].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
