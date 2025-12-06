#!/usr/bin/env python3

from memory_retrieval import (
    query_semantic,
    query_episodic,
    query_procedural,
    print_memories,
)

def main():
    sem = query_semantic("Where does Evert live and what region is that in?", k=5)
    epi = query_episodic("Tell me about the Gobabis trip", k=5)
    pro = query_procedural("How do I set up llm-thalamus?", k=5)

    print_memories("Semantic", "Where does Evert live and what region is that in?", sem)
    print_memories("Episodic", "Tell me about the Gobabis trip", epi)
    print_memories("Procedural", "How do I set up llm-thalamus?", pro)

if __name__ == "__main__":
    main()
