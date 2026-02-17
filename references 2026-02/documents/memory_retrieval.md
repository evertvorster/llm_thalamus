# llm-thalamus – Memory Retrieval Guide

This document describes **how llm-thalamus retrieves memories from Cavira’s OpenMemory** using the **advanced automatic memory interface**.

We cover:

- Sector-based retrieval  
- Semantic retrieval  
- Filters  
- User ID scoping  
- How llm-thalamus will later integrate retrieval recipes  

---

## 1. Retrieval Workflow

1. User submits a message.  
2. llm-thalamus (optionally) asks the LLM for a **retrieval plan**.  
3. llm-thalamus executes queries using:
   - semantic search  
   - sectors  
   - tags  
   - userId  
4. Retrieved memories are fed into the answer-generation call.  

---

## 2. Retrieval API: `mem.query(...)`

### Signature:

```python
results = mem.query(query, k=None, filters=None)
```

Parameters:

- **query** → natural language semantic query  
- **k** → top-k limit  
- **filters** →
  - `user_id`
  - `sectors`
  - `tags`

Return value: list of dict-like memories containing fields like:

- id  
- text/content  
- primarySector  
- sectors  
- score  
- metadata  
- userId  

---

## 3. Example Retrieval Script: `query_memory_types.py`

```python
#!/usr/bin/env python3

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
    print(f"
=== Sector: {sector} ===")
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

        print(f"
[{i}] ---------------------------")
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
```

---

## 4. Sector-Based Retrieval

Sector filters:

- `"semantic"` → persona and stable facts  
- `"episodic"` → time-bound stories or events  
- `"procedural"` → how-to or multi-step processes  

Sector filtering ensures retrieval aligns with memory structure OpenMemory inferred.

---

## 5. User Scoping

All retrievals include:

```python
filters={"user_id": user_id}
```

This prevents cross-user contamination and allows multi-user systems.

---

## 6. Future Integration: Retrieval Recipes

Eventually, llm-thalamus will support:

### LLM → Retrieval Plan (JSON)

Example:

```json
{
  "retrieve":[
    {"sector": "semantic", "k": 5},
    {"sector": "episodic", "k": 3},
    {"sector": "procedural", "k": 3}
  ]
}
```

llm-thalamus will:

1. Parse plan  
2. Run each query with correct filters  
3. Merge, dedupe, and score  
4. Feed memory bundle to the LLM  

---

# END OF DOCUMENT
