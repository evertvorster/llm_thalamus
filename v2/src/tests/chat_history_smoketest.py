from pathlib import Path

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
