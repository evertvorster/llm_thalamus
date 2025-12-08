#!/usr/bin/env python3
"""
test_document_retrieval.py

Diagnostic script for the Spaces → Documents pipeline.

Run from the inner project root (the one that has spaces_manager.py):

    cd llm_thalamus
    python tests/test_document_retrieval.py

It will:
- Connect to spaces.db via spaces_manager.
- Print all Spaces, Objects, and Versions.
- Call get_active_documents_for_prompt() and print the docs that would be
  supplied to Thalamus (name + text snippet).
"""

from __future__ import annotations

import sys
from pathlib import Path
import textwrap

# ---------------------------------------------------------------------------
# Make the package directory (which contains spaces_manager.py) importable
# ---------------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
PACKAGE_DIR = THIS_FILE.parents[1]  # /.../llm_thalamus/llm_thalamus

if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

import spaces_manager  # noqa: E402


def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    manager = spaces_manager.get_manager()

    # ----------------------------------------------------------------------
    # Basic DB info
    # ----------------------------------------------------------------------
    print_header("Spaces DB Info")
    try:
        db_path = spaces_manager._get_db_path()  # type: ignore[attr-defined]
    except Exception:
        db_path = "<unknown> (no _get_db_path in spaces_manager)"
    print(f"Spaces DB path: {db_path}")

    # ----------------------------------------------------------------------
    # Spaces
    # ----------------------------------------------------------------------
    print_header("Spaces")
    spaces = manager.list_spaces(active_only=False)
    if not spaces:
        print("No spaces found.")
    else:
        for s in spaces:
            status = "ACTIVE" if s.active else "inactive"
            print(f"- Space #{s.id} [{status}] '{s.name}' (created {s.created_at})")
            if s.description:
                print(f"    Description: {s.description}")

    # ----------------------------------------------------------------------
    # Objects per space
    # ----------------------------------------------------------------------
    print_header("Objects")
    if not spaces:
        print("No spaces → no objects.")
    else:
        for s in spaces:
            print(f"\nSpace #{s.id} '{s.name}':")
            objs = manager.list_objects(space_id=s.id, active_only=False)
            if not objs:
                print("  (no objects)")
                continue
            for o in objs:
                status = "ACTIVE" if o.active else "inactive"
                print(
                    f"  - Object #{o.id} [{status}] '{o.name}' "
                    f"(type={o.object_type}, created {o.created_at})"
                )

    # ----------------------------------------------------------------------
    # Versions per object
    # ----------------------------------------------------------------------
    print_header("Versions")
    if not spaces:
        print("No spaces → no versions.")
    else:
        for s in spaces:
            objs = manager.list_objects(space_id=s.id, active_only=False)
            if not objs:
                continue
            print(f"\nSpace #{s.id} '{s.name}':")
            for o in objs:
                print(f"  Object #{o.id} '{o.name}':")
                versions = manager.list_versions(o.id)
                if not versions:
                    print("    (no versions)")
                    continue
                for v in versions:
                    print(
                        f"    - Version #{v.id} "
                        f"[status={v.status}] "
                        f"ingested_at={v.ingested_at}, "
                        f"filename={v.filename}"
                    )
                    print(f"      original_path: {v.original_path}")
                    print(f"      openmemory_id: {v.openmemory_id}")

    # ----------------------------------------------------------------------
    # Documents that would be supplied to Thalamus
    # ----------------------------------------------------------------------
    print_header("Documents supplied to Thalamus (get_active_documents_for_prompt)")
    try:
        docs = manager.get_active_documents_for_prompt()
    except Exception as e:
        print(f"Error calling get_active_documents_for_prompt(): {e}")
        return

    if not docs:
        print("No active documents returned.")
        return

    for idx, doc in enumerate(docs, start=1):
        name = str(doc.get("name") or doc.get("filename") or "(unnamed)")
        text = str(doc.get("text") or doc.get("content") or "")
        snippet = textwrap.shorten(text, width=400, placeholder=" …")
        print(f"\nDocument #{idx}: {name}")
        print("-" * 40)
        if text:
            print(snippet)
        else:
            print("(no text content in document dict)")


if __name__ == "__main__":
    main()
