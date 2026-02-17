from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _maybe_set_env(key: str, value: Optional[str]) -> None:
    if value is None:
        return
    if isinstance(value, str) and value.strip():
        os.environ[key] = value.strip()


def sqlite_db_url(path: Path) -> str:
    # sqlite:////abs/path form
    p = path.expanduser().resolve()
    return "sqlite:///" + str(p)


def apply_openmemory_env_for_python_sdk(
    *,
    db_path: Path,
    tier: str,
    embeddings_provider: str,
    embeddings_model: str,
    embeddings_ollama_url: str,
) -> None:
    """
    Configure OpenMemory via environment variables (as per old codebase). :contentReference[oaicite:4]{index=4}
    """
    _maybe_set_env("OM_DB_URL", sqlite_db_url(db_path))
    _maybe_set_env("OM_DB_PATH", str(db_path.expanduser().resolve()))

    # Sectoring / tier behaviour.
    _maybe_set_env("OM_TIER", tier)

    # Embedding provider selection.
    if embeddings_provider != "ollama":
        raise NotImplementedError(
            f"Only ollama embeddings are supported in v2 bootstrap for now; got {embeddings_provider!r}"
        )

    _maybe_set_env("OM_EMBED_KIND", "ollama")
    _maybe_set_env("OM_EMBEDDINGS", "ollama")  # legacy/back-compat style

    _maybe_set_env("OM_OLLAMA_EMBEDDING_MODEL", embeddings_model)
    _maybe_set_env("OM_OLLAMA_MODEL", embeddings_model)  # legacy/back-compat style

    _maybe_set_env("OLLAMA_URL", embeddings_ollama_url)
