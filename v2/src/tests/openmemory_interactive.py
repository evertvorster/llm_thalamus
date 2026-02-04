from __future__ import annotations

from typing import Any, Dict, List, Optional

from thalamus_openmemory.api import add_memory, search_memories
from thalamus_openmemory.api.client import OpenMemoryClient


def _extract_text(item: Dict[str, Any]) -> str:
    for k in ("content", "text", "memory", "value"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return str(item)[:200]


def _extract_score(item: Dict[str, Any]) -> str:
    v = item.get("score")
    if v is None:
        return ""
    try:
        return f"{float(v):.3f}"
    except Exception:
        return str(v)


def _extract_sector(item: Dict[str, Any]) -> str:
    """
    Deep tier usually attaches a sector. In your older codebase this was often
    exposed as PrimarySector / sector / memory_type (varies by backend/version).

    We check common keys first, then check metadata.
    """
    # direct fields
    for k in ("PrimarySector", "primary_sector", "sector", "memory_type", "type"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # nested metadata
    md = item.get("metadata")
    if isinstance(md, dict):
        for k in ("PrimarySector", "primary_sector", "sector", "memory_type", "type", "content_type"):
            v = md.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return "?"


def _format_result(i: int, item: Dict[str, Any]) -> str:
    score = _extract_score(item)
    sector = _extract_sector(item)
    text = _extract_text(item)

    # Keep output tight: sector + score + first line
    if score:
        return f"  {i}. [{sector}] ({score}) {text}"
    return f"  {i}. [{sector}] {text}"


def run_openmemory_interactive_test(
    client: OpenMemoryClient,
    *,
    user_id: Optional[str] = None,
    k: int = 5,
) -> int:
    """
    Interactive loop:
      - prompt for text
      - search for related memories first
      - print top-k results (sector + optional score + content)
      - then store the entered text
      - repeat until escape sequence

    Exit conditions:
      - Ctrl-D (EOF)
      - Ctrl-C
      - input is one of: ':q', 'quit', 'exit'
      - empty input (just press Enter)
    """
    print("\n== OpenMemory interactive test ==")
    print("Search happens BEFORE storing the entered text.")
    print("Exit with empty line, Ctrl-D, Ctrl-C, ':q', 'quit', or 'exit'.\n")

    while True:
        try:
            s = input("> ").strip()
        except EOFError:
            print("\nEOF -> exiting test.")
            return 0
        except KeyboardInterrupt:
            print("\n^C -> exiting test.")
            return 0

        if s == "" or s.lower() in {":q", "quit", "exit"}:
            print("Exiting test.")
            return 0

        # 1) search FIRST
        try:
            results: List[Dict[str, Any]] = search_memories(client, s, k=k, user_id=user_id)
        except Exception as e:
            print(f"[ERROR] search_memories failed: {type(e).__name__}: {e}")
            return 1

        if not results:
            print("[search] 0 results")
        else:
            print(f"[search] top {min(k, len(results))} results:")
            for i, item in enumerate(results[:k], start=1):
                print(_format_result(i, item))

        # 2) store AFTER displaying search
        try:
            _ = add_memory(
                client,
                s,
                user_id=user_id,
                metadata={"kind": "interactive_test"},
                tags=["interactive_test"],
            )
            print("[stored]\n")
        except Exception as e:
            print(f"[ERROR] add_memory failed: {type(e).__name__}: {e}")
            return 1
