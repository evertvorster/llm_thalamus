#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import os
import pkgutil
import sys
import traceback
from pathlib import Path


def _ensure_src_on_path(repo_root: Path) -> None:
    src = (repo_root / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _iter_probe_modules(pkg_name: str):
    """
    Yield fully-qualified module names under pkg_name.
    """
    pkg = importlib.import_module(pkg_name)
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.ispkg:
            continue
        if not mod.name.startswith("probe_"):
            continue
        yield f"{pkg_name}.{mod.name}"


def _run_probe_module(mod_name: str) -> int:
    """
    Convention:
      - If module defines main() -> int, call it.
      - Else, importing the module is considered success.
    """
    m = importlib.import_module(mod_name)
    fn = getattr(m, "main", None)
    if callable(fn):
        rc = fn()
        return int(rc) if rc is not None else 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all llm-thalamus dev probes.")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at first failing probe.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List discovered probes without running them.",
    )
    parser.add_argument(
        "--pattern",
        default="",
        help="Only run probes whose module name contains this substring.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    _ensure_src_on_path(repo_root)

    # Optional: set dev mode for the probe run without requiring the caller to export it
    # (comment out if you prefer explicit shell env)
    # os.environ.setdefault("LLM_THALAMUS_DEV", "1")

    pkg_name = "llm_thalamus.tools_dev.probes"
    mods = sorted(_iter_probe_modules(pkg_name))

    if args.pattern:
        mods = [m for m in mods if args.pattern in m]

    if args.list:
        for m in mods:
            print(m)
        return 0

    if not mods:
        print("No probes found.")
        return 0

    failures: list[tuple[str, str]] = []
    for mod_name in mods:
        print(f"==> {mod_name}")
        try:
            rc = _run_probe_module(mod_name)
            if rc != 0:
                failures.append((mod_name, f"returned rc={rc}"))
                print(f"FAIL: {mod_name} (rc={rc})")
                if args.fail_fast:
                    break
            else:
                print(f"OK:   {mod_name}")
        except Exception as e:
            tb = traceback.format_exc()
            failures.append((mod_name, tb))
            print(f"EXCEPTION: {mod_name}: {e}")
            if args.fail_fast:
                break
        print()

    if failures:
        print("Summary: FAIL")
        for mod, info in failures:
            print(f"- {mod}")
            # Keep output readable; full trace is still available above
            if "Traceback" not in info:
                print(f"  {info}")
        return 1

    print("Summary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
