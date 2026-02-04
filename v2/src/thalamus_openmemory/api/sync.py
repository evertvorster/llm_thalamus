from __future__ import annotations

import asyncio
from typing import Any, Awaitable


def run_async(coro: Awaitable[Any]) -> Any:
    """
    Run an async OpenMemory call from synchronous code.

    Mirrors the old pattern. :contentReference[oaicite:3]{index=3}
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        raise RuntimeError(
            "run_async() called while an asyncio event loop is already running in this thread. "
            "Call OpenMemory with 'await' from async code, or move OpenMemory calls to a worker."
        )
    return asyncio.run(coro)
