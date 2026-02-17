# llm-thalamus – Memory Storage Guide

This document describes **how llm-thalamus stores memories into Cavira’s OpenMemory**, using the **advanced automatic memory interface**.

The goal is:

- To **minimize hand-crafted logic** in llm-thalamus.
- To **trust OpenMemory’s internal classification and decay mechanisms**.
- To define a **clear, repeatable pattern** for writing different *kinds* of memories (semantic, episodic, procedural, etc.) without micromanaging sectors.

This guide is deliberately verbose so future work can be done **without re-reading the original OpenMemory docs**.

---

## 1. High-Level Design

### 1.1 llm-thalamus’ role

llm-thalamus is a **controller / middleware** sitting between:

- A **user-facing LLM**, and  
- A **local OpenMemory instance**.

At storage time, llm-thalamus:

1. Receives:
   - User message(s)
   - LLM responses
   - Metadata (timestamps, session IDs, etc.)
   - Potentially a **reflection / storage recipe** from the LLM.

2. Decides *what* to store:
   - Persona and preferences  
   - Long-term facts  
   - Episodic events  
   - Procedures  
   - Potentially summaries or structural memories  

3. Delegates storage to OpenMemory:
   - We call the **high-level `.add()` API** and allow OpenMemory to:
     - Embed the text  
     - Auto-classify memory into sectors  
     - Update salience  
     - Handle decay  

**Rule: llm-thalamus never manually sets `primarySector` or `sectors`.**

We rely entirely on OpenMemory's internal classification.

---

## 2. Configuration and Setup

### 2.1 Config file: `config/config.json`

```json
{
  "thalamus": {
    "project_name": "llm-thalamus",
    "default_user_id": "default"
  },
  "openmemory": {
    "mode": "local",
    "path": "./data/memory.sqlite",
    "tier": "smart"
  },
  "embeddings": {
    "provider": "ollama",
    "model": "nomic-embed-text",
    "ollama_url": "http://localhost:11434"
  },
  "logging": {
    "level": "INFO",
    "file": "./logs/thalamus.log"
  }
}
```

### 2.2 Building a memory client

```python
from openmemory import OpenMemory
import json
from pathlib import Path

CONFIG_PATH = Path("config/config.json")

def load_config():
    with CONFIG_PATH.open() as f:
        return json.load(f)

def build_memory_client(cfg):
    om_cfg = cfg["openmemory"]
    emb_cfg = cfg["embeddings"]

    embeddings = {
        "provider": "ollama",
        "ollama": {
            "url": emb_cfg["ollama_url"]
        },
        "model": emb_cfg["model"]
    }

    return OpenMemory(
        path=om_cfg["path"],
        tier=om_cfg["tier"],
        embeddings=embeddings,
    )
```

---

## 3. Memory Types (Conceptual)

Although OpenMemory internally supports many nuanced types, we categorize them as:

- **Semantic** – stable facts
- **Episodic** – events in time
- **Procedural** – instructions/how-tos

Internally, OpenMemory adds:

- `primarySector`
- `sectors`  
- decay & reinforcement  
- contextual salience scoring  

We do **not** set sectors manually.

---

## 4. Storing Memory with `mem.add(...)`

### Example:

```python
mem.add(
    "Evert lives in Namibia.",
    tags=["persona", "location"],
    metadata={"source": "system"},
    userId="default"
)
```

Returns dict:

- content  
- id  
- score  
- primarySector  
- sectors  
- metadata  
- userId  

---

## 5. Full Example Script

This is the complete `write_memory_types.py` with semantic, episodic, and procedural storage:

```python
#!/usr/bin/env python3

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

    # --- 1) Semantic-style memory --------------------------------------------
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

    # --- 2) Episodic-style memory --------------------------------------------
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

    # --- 3) Procedural-style memory ------------------------------------------
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

    mem.close()


if __name__ == "__main__":
    main()
```

---

# END OF DOCUMENT
