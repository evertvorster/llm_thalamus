# seed_example.py
from memory_storage import store_semantic, store_episodic, store_procedural

store_semantic("Evert lives in Namibia.", tags=["persona", "location"])
store_episodic(
    "On 2024-07-05, Evert drove from the Namibian coast to Gobabis...",
    date="2024-07-05",
    location="Gobabis, Namibia",
)
store_procedural(
    "To set up llm-thalamus in development mode: ...",
    topic="llm-thalamus setup",
)
