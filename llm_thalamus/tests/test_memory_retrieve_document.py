#!/usr/bin/env python3

from memory_retrieve_documents import retrieve_document_from_metadata


def main():
    meta = {
        "filename": "memory_storage.md",
        "topic": "llm-thalamus memory design",
        "note": "File supplied during thalamus design session",
        # The LLM can either include these explicitly...
        "tags": ["llm-thalamus", "docs", "design"],
    }

    # 1) Normal behaviour: get the latest ingested version
    latest_text = retrieve_document_from_metadata(meta)

    print("\n=== Latest Version ===\n")
    print(latest_text)

    # 2) Temporal behaviour: get the last version that existed at/as-of this time.
    #
    # Adjust this timestamp to something meaningful for your tests, e.g.
    # slightly before or after a known re-ingest of the same document.
    as_of = "2025-12-04T09:00:00+00:00"

    as_of_text = retrieve_document_from_metadata(
        meta,
        as_of=as_of,  # controller-level time-travel knob
        # strategy="latest",  # optional; defaults to "latest"
    )

    print(f"\n=== Version as of {as_of} ===\n")
    print(as_of_text)


if __name__ == "__main__":
    main()
