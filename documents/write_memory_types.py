#!/usr/bin/env python3
"""
Seed the OpenMemory database with one example of each memory *sector*:
- semantic   : general fact / stable knowledge
- episodic   : specific event in time
- procedural : how-to / steps

We rely on OpenMemory's advanced automatic classification (primarySector + sectors)
and do NOT manually specify sectors – we just pass content, tags, metadata, userId.
"""

import json
from pathlib import Path

from openmemory import OpenMemory


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.json"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_memory_client(cfg: dict) -> OpenMemory:
    om_cfg = cfg["openmemory"]
    emb_cfg = cfg["embeddings"]

    # Build embeddings config according to provider.
    # We only implement "ollama" for now.
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


def main() -> None:
    cfg = load_config()
    user_id = cfg["thalamus"]["default_user_id"]
    mem = build_memory_client(cfg)

    # 1) Semantic-style: stable fact about the user.
    semantic_text = (
        "Evert lives in Namibia, a country in southern Africa, and often works on "
        "Linux and AI projects from there."
    )
    semantic_result = mem.add(
        semantic_text,
        tags=["persona", "location", "semantic-demo"],
        metadata={
            "kind": "semantic_example",
            "source": "write_memory_types.py",
        },
        userId=user_id,
    )
    print("Semantic memory added:")
    print(semantic_result)
    print()

    # 2) Episodic-style: specific event with time and place.
    episodic_text = (
        "On 2024-07-05, Evert drove from the Namibian coast to Gobabis to scout "
        "for potential property to buy near the town."
    )
    episodic_result = mem.add(
        episodic_text,
        tags=["episodic-demo", "travel", "property"],
        metadata={
            "kind": "episodic_example",
            "date": "2024-07-05",
            "location": "Gobabis, Namibia",
            "source": "write_memory_types.py",
        },
        userId=user_id,
    )
    print("Episodic memory added:")
    print(episodic_result)
    print()

    # 3) Procedural-style: instructions / how-to.
    procedural_text = (
        "To set up llm-thalamus in development mode: "
        "1) Create config/config.json with OpenMemory and Ollama settings. "
        "2) Run write_memory_types.py to seed example memories. "
        "3) Run query_memory_types.py to verify retrieval by sector."
    )
    procedural_result = mem.add(
        procedural_text,
        tags=["procedural-demo", "howto", "llm-thalamus"],
        metadata={
            "kind": "procedural_example",
            "topic": "llm-thalamus setup",
            "source": "write_memory_types.py",
        },
        userId=user_id,
    )
    print("Procedural memory added:")
    print(procedural_result)
    print()

    # If you prefer, you can explicitly close:
    mem.close()


if __name__ == "__main__":
    main()
