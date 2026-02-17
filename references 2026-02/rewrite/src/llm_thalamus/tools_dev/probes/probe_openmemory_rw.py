from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _safe_get_env(keys: Iterable[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for k in keys:
        out[k] = os.environ.get(k)
    return out


def _call_if_callable(v: Any) -> Any:
    return v() if callable(v) else v


def _resolve_cfg_values(cfg: Any) -> Dict[str, Any]:
    # Handle both attributes and methods (your config evolved a few times)
    db_path = None
    if hasattr(cfg, "openmemory_db_path"):
        db_path = _call_if_callable(getattr(cfg, "openmemory_db_path"))

    db_url = None
    if hasattr(cfg, "openmemory_db_url"):
        db_url = _call_if_callable(getattr(cfg, "openmemory_db_url"))

    tier = None
    if hasattr(cfg, "openmemory") and cfg.openmemory is not None:
        tier = getattr(cfg.openmemory, "tier", None)

    embed_provider = getattr(cfg, "embeddings_provider", None)
    embed_model = getattr(cfg, "embeddings_model", None)
    ollama_url = getattr(cfg, "ollama_url", None)

    return {
        "db_path": str(db_path) if db_path is not None else None,
        "db_url": str(db_url) if db_url is not None else None,
        "tier": str(tier) if tier is not None else None,
        "embeddings_provider": str(embed_provider) if embed_provider is not None else None,
        "embeddings_model": str(embed_model) if embed_model is not None else None,
        "ollama_url": str(ollama_url) if ollama_url is not None else None,
    }


def run() -> None:
    """
    Probe: OpenMemory read/write with verbose config+env diagnostics.

    Rules:
    - validate real runtime state (DB exists where config says)
    - print applied settings (config-derived + env vars)
    - then do a tiny write+delete roundtrip
    """
    from llm_thalamus.config.access import get_config
    from llm_thalamus.adapters.openmemory import client as om_client

    cfg = get_config()

    # --- Pre-flight: show config-derived settings ---
    vals = _resolve_cfg_values(cfg)

    print("probe_openmemory_rw: DIAGNOSTICS")
    for k in (
        "db_path",
        "db_url",
        "tier",
        "embeddings_provider",
        "embeddings_model",
        "ollama_url",
    ):
        print(f"  cfg.{k}={vals.get(k)}")

    # --- Pre-flight: does the DB exist where config says it should? ---
    if vals["db_path"] is None:
        raise RuntimeError("Config did not provide openmemory_db_path()")

    db_path = Path(vals["db_path"]).expanduser()
    # do not resolve relative here; schema/paths should have anchored it already
    print(f"  db_path_exists={db_path.exists()}  is_file={db_path.is_file()}")

    if not db_path.exists():
        raise FileNotFoundError(
            "OpenMemory sqlite DB not found at expected path:\n"
            f"  {db_path}\n"
            "Fix: copy/restore the database to this location (or adjust config/path policy)."
        )

    # --- Snapshot: CWD default db presence check ---
    cwd_default_db = Path("openmemory.db")
    print(f"  cwd_openmemory_db_preexists={cwd_default_db.exists()}  path={cwd_default_db.resolve()}")

    # --- Force adapter to configure env + create client ---
    # (This is the crucial moment; after this we print env)
    mem = om_client.get_memory()

    # --- Print env vars after adapter configuration ---
    env_keys = [
        "OM_DB_URL",
        "OM_TIER",
        "OM_EMBEDDINGS_PROVIDER",
        "OM_OLLAMA_URL",
        "OM_OLLAMA_EMBEDDING_MODEL",
        "OM_OLLAMA_EMBEDDINGS_MODEL",
        "OM_OLLAMA_EMBED_MODEL",
        "OLLAMA_URL",
    ]
    env = _safe_get_env(env_keys)
    print("  env_after_client_init:")
    for k in env_keys:
        print(f"    {k}={env.get(k)}")

    print(f"  cwd_openmemory_db_after_init={cwd_default_db.exists()}")

    # --- Basic roundtrip write+delete (you said writes are OK) ---
    # Use a deterministic marker so you can spot it if something goes wrong.
    user_id = om_client.get_default_user_id()
    content = "PROBE: openmemory rw check (throwaway)"
    created_id = None

    # The adapter has both sync helpers; use them to ensure we hit the same code path.
    created = om_client.add(
        content,
        user_id=user_id,
        memory_type="semantic",
        metadata={"probe": True},
        tags=["probe", "openmemory"],
    )

    # Try to extract ID in a version-tolerant way
    if isinstance(created, dict):
        created_id = created.get("id") or created.get("memory_id") or created.get("uuid")
    elif isinstance(created, str):
        created_id = created

    print("probe_openmemory_rw: WRITE")
    print(f"  wrote=yes  id={created_id}")

    if created_id:
        om_client.delete(created_id)
        print("probe_openmemory_rw: DELETE")
        print("  deleted=yes")
    else:
        print("probe_openmemory_rw: DELETE")
        print("  deleted=skip (could not parse id)")

    print("probe_openmemory_rw: OK")


if __name__ == "__main__":
    run()
