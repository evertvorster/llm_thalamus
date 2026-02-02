from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openmemory import Memory

from llm_thalamus.config.access import get_config

_MEM: Optional[Memory] = None
_OM_ENV_LOGGED: bool = False


def _get_cfg() -> Any:
    return get_config()


def _call_if_callable(v: Any) -> Any:
    return v() if callable(v) else v


def _cfg_openmemory_db_path(cfg: Any) -> Path:
    """
    Supports both:
      - cfg.openmemory_db_path() -> Path
      - cfg.openmemory_db_path  -> Path/str
    """
    v = getattr(cfg, "openmemory_db_path", None)
    if v is None:
        raise RuntimeError("Config missing required field/method: openmemory_db_path")

    v = _call_if_callable(v)

    # v may already be a Path; Path(Path) is fine
    return Path(v)


def _cfg_openmemory_db_url(cfg: Any) -> str:
    """
    Supports both:
      - cfg.openmemory_db_url() -> str
      - cfg.openmemory_db_url  -> str
    """
    v = getattr(cfg, "openmemory_db_url", None)
    if v is None:
        raise RuntimeError("Config missing required field/method: openmemory_db_url")

    v = _call_if_callable(v)
    return str(v)


def _cfg_default_user_id(cfg: Any) -> Optional[str]:
    # In your schema, default_user_id lives at the top-level.
    v = getattr(cfg, "default_user_id", None)
    return str(v) if v else None


def _cfg_embeddings_provider(cfg: Any) -> str:
    v = getattr(cfg, "embeddings_provider", None)
    return str(v) if v else ""


def _cfg_embeddings_model(cfg: Any) -> Optional[str]:
    v = getattr(cfg, "embeddings_model", None)
    return str(v) if v else None


def _cfg_ollama_url(cfg: Any) -> str:
    v = getattr(cfg, "ollama_url", None)
    if not v:
        raise RuntimeError("Config missing required field: ollama_url")
    return str(v)


def _cfg_openmemory_tier(cfg: Any) -> str:
    om = getattr(cfg, "openmemory", None)
    tier = getattr(om, "tier", None) if om is not None else None
    if not tier:
        return "default"
    return str(tier)


def _cfg_openmemory_ollama_model(cfg: Any) -> Optional[str]:
    om = getattr(cfg, "openmemory", None)
    model = getattr(om, "ollama_model", None) if om is not None else None
    return str(model) if model else None


def assert_db_present() -> Path:
    """
    Strict, real-state validation:
    - The DB must exist at the config-derived path.
    - Fail loudly if missing (your intended workflow).
    """
    cfg = _get_cfg()
    db_path = _cfg_openmemory_db_path(cfg)

    if not db_path.exists():
        raise FileNotFoundError(
            "OpenMemory sqlite DB not found.\n"
            f"Expected path: {db_path}\n"
            "Fix: copy/restore the database to this location (or adjust config/path policy)."
        )
    if not db_path.is_file():
        raise FileNotFoundError(
            "OpenMemory sqlite DB path exists but is not a file.\n"
            f"Expected path: {db_path}"
        )
    return db_path


def get_default_user_id() -> Optional[str]:
    cfg = _get_cfg()
    return _cfg_default_user_id(cfg)


def _configure_openmemory_env() -> None:
    """
    Configure OpenMemory SDK via env vars, using typed config.
    Preserves old behavior:
    - Enforces embeddings provider = 'ollama' if set
    - Sets OM_DB_URL / OM_TIER / embeddings model and Ollama URL
    - Compatibility shim for SDK config env attribute name changes
    """
    global _OM_ENV_LOGGED

    cfg = _get_cfg()

    provider = _cfg_embeddings_provider(cfg).strip().lower()
    if provider and provider != "ollama":
        raise RuntimeError(
            f"Unsupported embeddings provider '{provider}'. "
            "This migration currently supports provider='ollama' only."
        )

    db_url = _cfg_openmemory_db_url(cfg)
    tier = _cfg_openmemory_tier(cfg)

    # Choose embedding model:
    # 1) embeddings_model from config
    # 2) openmemory.ollama_model
    # 3) fallback default
    embed_model = _cfg_embeddings_model(cfg) or _cfg_openmemory_ollama_model(cfg) or "nomic-embed-text:latest"
    ollama_url = _cfg_ollama_url(cfg)

    os.environ["OM_DB_URL"] = db_url
    os.environ["OM_TIER"] = tier

    os.environ["OM_EMBEDDINGS_PROVIDER"] = "ollama"
    os.environ["OM_OLLAMA_EMBEDDINGS_MODEL"] = embed_model
    os.environ["OM_OLLAMA_URL"] = ollama_url

    # Some OpenMemory versions also look at this:
    os.environ["OLLAMA_URL"] = ollama_url

    # Compatibility: openmemory.core.config.env may expose different attribute names.
    try:
        from openmemory.core.config import env as om_env  # type: ignore

        if hasattr(om_env, "ollama_base_url"):
            setattr(om_env, "ollama_base_url", ollama_url)
        elif hasattr(om_env, "ollama_url"):
            setattr(om_env, "ollama_url", ollama_url)
    except Exception:
        # Env vars are already set; don't hard-fail here.
        pass

    # Keep as a one-time toggle in case you later want to add a debug print/log here.
    if not _OM_ENV_LOGGED:
        _OM_ENV_LOGGED = True


def get_memory() -> Memory:
    """
    Singleton OpenMemory client.
    Note: does NOT enforce DB existence; OpenMemory can create a DB.
    Probes can call assert_db_present() when strict behavior is desired.
    """
    global _MEM
    if _MEM is not None:
        return _MEM

    _configure_openmemory_env()
    _MEM = Memory()
    return _MEM


def run_om_async(awaitable: Any) -> Any:
    """
    Run an OpenMemory coroutine from sync code.

    Preserves old behavior:
    - If already inside a running event loop, fail loudly.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            raise RuntimeError(
                "Cannot run OpenMemory async operation inside a running event loop. "
                "Call async APIs directly in async context."
            )
    except RuntimeError:
        # No running loop - OK
        pass
    return asyncio.run(awaitable)


async def _search_async(mem: Memory, query: str, k: int, *, user_id: Optional[str] = None) -> Any:
    """
    OpenMemory SDK API drift shim:
    try k=, n=, limit= argument names.
    """
    kwargs: Dict[str, Any] = {}
    if user_id:
        kwargs["user_id"] = user_id

    for param in ("k", "n", "limit"):
        try:
            return await mem.search(query=query, **{param: int(k)}, **kwargs)
        except TypeError:
            continue

    return await mem.search(query=query, **kwargs)


def search(query: str, k: int = 8, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for OpenMemory search.
    Normalizes to list[dict].
    """
    mem = get_memory()
    result = run_om_async(_search_async(mem, query=query, k=int(k), user_id=user_id))

    if result is None:
        return []
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        r = result.get("results")
        if isinstance(r, list):
            return [x for x in r if isinstance(x, dict)]
    return []


async def _add_async(mem: Memory, content: str, **kwargs: Any) -> Any:
    return await mem.add(content, **kwargs)


def add(
    content: str,
    *,
    user_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Any:
    """
    Synchronous wrapper for OpenMemory add/write.
    """
    mem = get_memory()

    kwargs: Dict[str, Any] = {}
    if user_id:
        kwargs["user_id"] = user_id
    if memory_type:
        kwargs["memory_type"] = memory_type
    if metadata:
        kwargs["metadata"] = metadata
    if tags:
        kwargs["tags"] = tags

    return run_om_async(_add_async(mem, content, **kwargs))


async def _delete_async(mem: Memory, memory_id: str) -> Any:
    return await mem.delete(memory_id)


def delete(memory_id: str) -> None:
    """
    Synchronous wrapper for OpenMemory delete.
    """
    mem = get_memory()
    run_om_async(_delete_async(mem, memory_id))
