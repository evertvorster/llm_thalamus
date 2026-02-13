from __future__ import annotations

import queue
import threading
from collections.abc import Iterator

from orchestrator.deps import Deps
from orchestrator.events import Event
from orchestrator.graph_build import run_graph
from orchestrator.state import State


def run_turn_langgraph(state: State, deps: Deps) -> Iterator[Event]:
    q: queue.Queue[Event | None] = queue.Queue()

    def emit(ev: Event) -> None:
        q.put(ev)

    def worker_thread() -> None:
        try:
            run_graph(state, deps, emit)
        except Exception as e:
            emit({"type": "log", "text": f"\n[langgraph_runner] FAILED: {e}\n"})
        finally:
            q.put(None)

    threading.Thread(target=worker_thread, daemon=True).start()

    while True:
        ev = q.get()
        if ev is None:
            break
        yield ev
