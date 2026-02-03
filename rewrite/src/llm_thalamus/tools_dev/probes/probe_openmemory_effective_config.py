from __future__ import annotations

import importlib
import os
import sys
import traceback
from typing import Any


def _print_env(prefix: str) -> None:
    keys = [
        "OM_DB_URL",
        "OM_TIER",
        "OM_EMBEDDINGS_PROVIDER",
        "OM_OLLAMA_URL",
        "OM_OLLAMA_EMBEDDING_MODEL",
        "OM_OLLAMA_EMBEDDINGS_MODEL",
        "OLLAMA_URL",
        "LLM_THALAMUS_OM_CONFIGURED",
    ]
    print(prefix)
    for k in keys:
        print(f"  {k}={os.environ.get(k)!r}")


def _dump_openmemory_internal_config() -> None:
    """
    Best-effort introspection: prints whatever OpenMemory exposes.
    This is not guaranteed to exist across versions.
    """
    try:
        import openmemory  # noqa: F401
    except Exception as e:
        print(f"[om] import openmemory failed: {e!r}")
        return

    try:
        from importlib import metadata
        print("[om] openmemory version:", metadata.version("openmemory"))
    except Exception:
        pass

    try:
        import openmemory.core.config as cfg  # type: ignore
        print("[om] openmemory.core.config:", cfg.__file__)

        # Try common patterns: env/config/settings objects or factories
        cand_names = []
        for name in dir(cfg):
            low = name.lower()
            if low in ("env", "config", "settings"):
                cand_names.append(name)
            elif any(s in low for s in ("env", "config", "setting")):
                cand_names.append(name)

        seen = set()
        cand_names = [n for n in cand_names if not (n in seen or seen.add(n))]

        for name in cand_names[:12]:
            obj: Any = getattr(cfg, name, None)
            if obj is None:
                continue

            if callable(obj):
                try:
                    obj = obj()
                except Exception as e:
                    print(f"[om] {name}() raised: {e!r}")
                    continue

            d = getattr(obj, "__dict__", None)
            if not isinstance(d, dict):
                continue

            interesting = {}
            for k, v in d.items():
                lk = str(k).lower()
                if any(x in lk for x in ("tier", "embed", "embedding", "ollama", "model", "provider", "dim", "url", "openai")):
                    interesting[k] = v

            if interesting:
                print(f"[om] {name} ({type(obj).__name__}):")
                for k, v in sorted(interesting.items(), key=lambda kv: str(kv[0])):
                    print(f"  {k}={v!r}")

    except Exception as e:
        print(f"[om] openmemory.core.config introspection failed: {e!r}")


def main() -> int:
    try:
        print("probe_openmemory_effective_config: start")

        # 1) Detect whether openmemory was imported before adapter init
        pre = any(m == "openmemory" or m.startswith("openmemory.") for m in sys.modules.keys())
        print(f"[1/5] openmemory pre-imported? {pre}")

        _print_env("[2/5] env before adapter init:")

        # 2) Import adapter and force initialization
        print("[3/5] import adapters.openmemory.client and force init")
        from llm_thalamus.adapters.openmemory import client as om_client

        mem = om_client.get_memory()
        print("[debug] get_memory() returned:", type(mem))

        _print_env("[4/5] env after adapter init:")

        # 3) Dump OpenMemory internal config view (if any)
        print("[5/5] openmemory internal config view (best-effort):")
        _dump_openmemory_internal_config()

        # Hard assertions you care about:
        tier = os.environ.get("OM_TIER")
        provider = os.environ.get("OM_EMBEDDINGS_PROVIDER")
        model = os.environ.get("OM_OLLAMA_EMBEDDING_MODEL") or os.environ.get("OM_OLLAMA_EMBEDDINGS_MODEL")

        if tier is None:
            raise RuntimeError("OM_TIER is not set in-process after adapter init. Tier must be explicit for llm_thalamus.")
        if provider != "ollama":
            raise RuntimeError(f"OM_EMBEDDINGS_PROVIDER expected 'ollama', got {provider!r}")
        if not model or "nomic" not in model:
            raise RuntimeError(f"Expected nomic embed model in OM_OLLAMA_EMBEDDING_MODEL/OM_OLLAMA_EMBEDDINGS_MODEL, got {model!r}")

        print("probe_openmemory_effective_config: OK")
        return 0

    except Exception:
        print("probe_openmemory_effective_config: FAIL")
        traceback.print_exc()
        return 1
