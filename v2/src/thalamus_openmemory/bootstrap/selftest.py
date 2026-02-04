from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from thalamus_openmemory.api.client import OpenMemoryHealth


def _extract_id(created: Dict[str, Any]) -> Optional[str]:
    for k in ("id", "memoryId", "memory_id"):
        v = created.get(k)
        if v:
            return str(v)
    return None


async def _search_compat(mem, query: str, *, k: int, user_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    search() signature has varied; old code tried k/n/limit variants. :contentReference[oaicite:5]{index=5}
    """
    variants = []
    base = {"query": query}
    if user_id:
        base["user_id"] = user_id

    variants.append({**base, "k": k})
    variants.append({**base, "n": k})
    variants.append({**base, "limit": k})

    last_err: Optional[BaseException] = None
    for kwargs in variants:
        try:
            res = await mem.search(**kwargs)
            return list(res)
        except TypeError as e:
            last_err = e
            continue

    raise TypeError(f"OpenMemory search() signature mismatch; last error: {last_err}") from last_err


async def run_openmemory_selftest(mem, *, user_id: str) -> OpenMemoryHealth:
    """
    Bootstrap self-test contract:
      1) add a memory
      2) search for that content (must find it)
      3) run a normal lookup query (empty OK, but must not error)
      4) delete the created memory
    """
    marker = f"llm_thalamus_bootstrap_test::{int(time.time())}"
    created: Optional[Dict[str, Any]] = None
    mid: Optional[str] = None

    try:
        created = await mem.add(marker, user_id=user_id, metadata={"kind": "bootstrap_test"})
        mid = _extract_id(created)
        if not mid:
            return OpenMemoryHealth(ok=False, details=f"add() succeeded but returned no id: keys={list(created.keys())}")

        results = await _search_compat(mem, marker, k=5, user_id=user_id)
        found = False
        for r in results:
            content = r.get("content") or r.get("text") or ""
            if marker in str(content):
                found = True
                break
        if not found:
            return OpenMemoryHealth(
                ok=False,
                details=f"search() did not return the inserted marker memory (got {len(results)} results).",
            )

        # “Normal lookup”: empty is fine, errors are not.
        _ = await _search_compat(mem, "llm_thalamus_bootstrap_query_that_should_return_empty", k=5, user_id=user_id)

        # Delete test memory
        await mem.delete(mid)

        return OpenMemoryHealth(ok=True, details="OpenMemory bootstrap self-test passed.")
    except Exception as e:
        # Best-effort cleanup
        try:
            if mid:
                await mem.delete(mid)
        except Exception:
            pass
        return OpenMemoryHealth(ok=False, details=f"{type(e).__name__}: {e}")
