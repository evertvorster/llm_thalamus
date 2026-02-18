from __future__ import annotations

"""runtime.event_bus

Thread-safe event bus for a single turn.

Goals:
- Nodes can emit events while the graph is running.
- A consumer can iterate events in order, blocking until the turn finishes.
- No UI / Qt dependency in runtime.

Notes:
- We support two iteration modes:
  1) `events()` which runs until `close()` is called (sentinel-based).
  2) `events_live(is_done=...)` which runs until an external predicate is done AND the queue is empty.
     This is useful when you want to continue emitting additional events after the main graph finishes.
"""

from dataclasses import dataclass
from queue import Queue, Empty
from typing import Callable, Iterator, Optional

from runtime.events import TurnEvent


_SENTINEL = object()


@dataclass
class EventBus:
    _q: Queue[object]

    @classmethod
    def create(cls, *, maxsize: int = 0) -> "EventBus":
        return cls(_q=Queue(maxsize=maxsize))

    def emit(self, ev: TurnEvent) -> None:
        self._q.put(ev)

    def close(self) -> None:
        self._q.put(_SENTINEL)

    def poll(self, *, timeout_s: float = 0.0) -> Optional[TurnEvent]:
        try:
            item = self._q.get(timeout=timeout_s) if timeout_s else self._q.get_nowait()
        except Empty:
            return None

        if item is _SENTINEL:
            return None

        if not isinstance(item, dict) or item.get("v") is None:
            raise TypeError(f"EventBus received non-TurnEvent: {item!r}")

        return item  # type: ignore[return-value]

    def events(self, *, poll_timeout_s: float = 0.1) -> Iterator[TurnEvent]:
        """Yield events until the bus is closed via `close()`."""
        while True:
            try:
                item = self._q.get(timeout=poll_timeout_s)
            except Empty:
                continue

            if item is _SENTINEL:
                break

            if not isinstance(item, dict) or item.get("v") is None:
                raise TypeError(f"EventBus received non-TurnEvent: {item!r}")

            yield item  # type: ignore[misc]

    def events_live(self, *, is_done: Callable[[], bool], poll_timeout_s: float = 0.1) -> Iterator[TurnEvent]:
        """Yield events until `is_done()` and the queue drains.

        This does NOT require calling `close()`.
        """
        while True:
            try:
                item = self._q.get(timeout=poll_timeout_s)
            except Empty:
                if is_done():
                    break
                continue

            if item is _SENTINEL:
                # If somebody closed early, we stop.
                break

            if not isinstance(item, dict) or item.get("v") is None:
                raise TypeError(f"EventBus received non-TurnEvent: {item!r}")

            yield item  # type: ignore[misc]

        # Drain any residual events without blocking.
        while True:
            ev = self.poll(timeout_s=0.0)
            if ev is None:
                break
            yield ev
