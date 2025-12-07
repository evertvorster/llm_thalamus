#!/usr/bin/env python3
"""
retrieve_ingested_file.py

Retrieve the raw text content of a document previously ingested into OpenMemory.

Usage:
    python retrieve_ingested_file.py memory_storage.md

You can optionally tweak the TAGS constant below to match what you used
during ingestion (e.g. ["llm-thalamus", "docs", "design"]).
"""

import sys
from typing import List, Dict, Any

from memory_retrieval import _query_memories_raw

# Adjust these if you used different tags when calling ingest_file(...)
TAGS: List[str] = ["llm-thalamus", "docs", "design"]


def choose_best_candidate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    From a list of memory objects, choose the one most likely to be the
    ingested document.

    Heuristic: choose the memory with the longest content/text.
    """
    if not results:
        raise ValueError("No candidate memories to choose from.")

    def content_len(m: Dict[str, Any]) -> int:
        text = m.get("content") or m.get("text") or ""
        return len(text)

    return max(results, key=content_len)


def retrieve_document(filename: str) -> str:
    """
    Retrieve the ingested file by filename, using tag filters and a
    simple heuristic to pick the best candidate.
    """
    # Use the filename as the semantic query, and filter by our ingestion tags.
    results = _query_memories_raw(filename, k=10, tags=TAGS)

    if not results:
        raise ValueError(
            f"No memories found for filename={filename!r} with tags={TAGS!r}"
        )

    memory = choose_best_candidate(results)

    content = memory.get("content") or memory.get("text")
    if not content:
        raise ValueError("Selected memory has no content/text field.")

    return content


def main():
    if len(sys.argv) < 2:
        print("Usage: python retrieve_ingested_file.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]

    try:
        text = retrieve_document(filename)
        print("\n=== Retrieved Document ===\n")
        print(text)
    except Exception as e:
        print(f"Error retrieving document: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
