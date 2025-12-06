#!/usr/bin/env python3

from datetime import datetime, timezone

from memory_ingest import ingest_file

def main():
    meta = {
        "provider": "evert",
        "provided_at": datetime.now(timezone.utc).isoformat(),
        "topic": "llm-thalamus memory design",
        "note": "File supplied during thalamus design session",
    }

    result = ingest_file(
        "documents/memory_storage.md",
        metadata=meta,
        tags=["llm-thalamus", "docs", "design"],
    )
    print("Ingest response:")
    print(result)

if __name__ == "__main__":
    main()
