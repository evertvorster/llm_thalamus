# memory_k_selftest.py

from thalamus_openmemory.api import search_memories
from openmemory.client import Memory


def run_memory_k_selftest(query: str = "elephant") -> None:
    """
    Deterministic test:
    Verify that OpenMemory respects k.
    """

    print("\n[Memory K Self-Test]")
    print(f"Query: {query}\n")

    mem = Memory()

    for k in (5, 10, 100):
        results = search_memories(mem, query, k=k)
        print(f"k={k:<3} -> returned {len(results)} memories")

    print("\n[Self-Test Complete]\n")
