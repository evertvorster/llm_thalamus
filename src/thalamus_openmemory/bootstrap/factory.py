from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from thalamus_openmemory.api.client import OpenMemoryClient, OpenMemoryError, OpenMemoryHealth
from thalamus_openmemory.api.sync import run_async

from .env import apply_openmemory_env_for_python_sdk
from .selftest import run_openmemory_selftest


@dataclass(frozen=True)
class OpenMemoryBootstrapResult:
    ok: bool
    client: Optional[OpenMemoryClient] = None
    health: Optional[OpenMemoryHealth] = None
    error: str = ""


def _get_default_user_id(cfg) -> str:
    # Keep this “inside bootstrap” so runtime code doesn’t parse config.
    try:
        uid = str((cfg.raw.get("thalamus") or {}).get("default_user_id") or "").strip()
        return uid or "default"
    except Exception:
        return "default"


def init_openmemory(cfg) -> OpenMemoryBootstrapResult:
    """
    Instantiate OpenMemory (Python SDK path) and run a self-test:
      - write a memory
      - search for that memory
      - run a normal lookup (empty OK, error not OK)
      - delete the memory

    Any failure is returned to llm_thalamus as a structured result.
    """
    try:
        # MCP will be different later; for now only local/python-sdk is implemented.
        if cfg.openmemory_endpoint_kind != "local":
            return OpenMemoryBootstrapResult(
                ok=False,
                error=f"OpenMemory endpoint.kind={cfg.openmemory_endpoint_kind!r} is not implemented in v2 yet.",
            )

        apply_openmemory_env_for_python_sdk(
            db_path=cfg.openmemory_db_path,
            tier=cfg.openmemory_tier,
            embeddings_provider=cfg.embeddings_provider,
            embeddings_model=cfg.embeddings_model,
            embeddings_ollama_url=cfg.embeddings_ollama_url,
        )

        # Construct client from SDK
        from openmemory.client import Memory  # import after env is set

        mem = Memory()

        # Self-test (critical)
        user_id = _get_default_user_id(cfg)
        health = run_async(run_openmemory_selftest(mem, user_id=user_id))
        if not health.ok:
            return OpenMemoryBootstrapResult(ok=False, error=health.details, health=health)

        return OpenMemoryBootstrapResult(ok=True, client=mem, health=health)

    except Exception as e:
        return OpenMemoryBootstrapResult(ok=False, error=f"{type(e).__name__}: {e}")
