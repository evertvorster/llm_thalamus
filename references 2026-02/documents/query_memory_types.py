#!/usr/bin/env python3
"""
Query the OpenMemory database for each sector type:
- semantic
- episodic
- procedural

We use mem.query(...) with filters={"sectors": [...], "user_id": ...}
to let OpenMemory's advanced system pick the right memories per sector.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

from openmemory import OpenMemory


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.json"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_memory_client(cfg: dict) -> OpenMemory:
    om_cfg = cfg["openmemory"]
    emb_cfg = cfg["embeddings"]

    provider = emb_cfg["provider"]
    if provider != "ollama":
        raise NotImplementedError(f"Only 'ollama' embeddings are implemented, got: {provider}")

    embeddings = {
        "provider": "ollama",
        "ollama": {
            "url": emb_cfg.get("ollama_url", "http://localhost:11434"),
        },
        "model": emb_cfg["model"],
    }

    mem = OpenMemory(
        path=om_cfg["path"],
        tier=om_cfg.get("tier", "smart"),
        embeddings=embeddings,
    )
    return mem


def print_results(sector: str, results: List[Dict[str, Any]]) -> None:
    print(f"\n=== Sector: {sector} ===")
    if not results:
        print("No memories found for this sector.")
        return

    for i, m in enumerate(results, start=1):
        content = m.get("content") or m.get("text") or ""
        primary_sector = m.get("primarySector")
        sectors = m.get("sectors")
        tags = m.get("tags")
        metadata = m.get("metadata")
        score = m.get("score")

        print(f"\n[{i}] ---------------------------")
        if score is not None:
            print(f"Score:         {score:.4f}")
        print(f"PrimarySector: {primary_sector}")
        print(f"Sectors:       {sectors}")
        print(f"Tags:          {tags}")
        print(f"Content:       {content}")
        if metadata is not None:
            print(f"Metadata:      {metadata}")


def main() -> None:
    cfg = load_config()
    user_id = cfg["thalamus"]["default_user_id"]
    mem = build_memory_client(cfg)

    # Queries tuned to roughly match the seeded memories semantically.
    queries_by_sector = {
        "semantic": "Where does Evert live and what region is that in?",
        "episodic": "Tell me about a specific trip Evert took to scout property.",
        "procedural": "How do I set up llm-thalamus for development?",
    }

    for sector, query in queries_by_sector.items():
        filters = {
            "sectors": [sector],
            "user_id": user_id,
        }
        results = mem.query(query, k=5, filters=filters)
        print_results(sector, results)

    mem.close()


if __name__ == "__main__":
    main()
