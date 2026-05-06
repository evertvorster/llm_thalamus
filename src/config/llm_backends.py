from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import tempfile
from typing import Any


def load_llm_backends_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"llm_backends.json not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return normalize_llm_backends_config(raw)


def save_llm_backends_config(path: Path, backends_config: dict[str, Any]) -> None:
    normalized = normalize_llm_backends_config(backends_config)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=".llm_backends.json.",
        dir=path.parent,
        delete=False,
    ) as tf:
        tmp_path = Path(tf.name)

    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists() and tmp_path != path:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def normalize_llm_backends_config(raw: dict[str, Any]) -> dict[str, Any]:
    backends = raw.get("backends", {}) if isinstance(raw, dict) else {}
    if not isinstance(backends, dict):
        raise ValueError("llm_backends.json: backends must be an object")

    normalized_backends: dict[str, Any] = {}
    for backend_id, backend_cfg in backends.items():
        if not isinstance(backend_id, str) or not isinstance(backend_cfg, dict):
            continue
        normalized_backends[backend_id] = _normalize_backend_config(backend_cfg)

    return {"backends": normalized_backends}


def _normalize_backend_config(backend_cfg: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("label", "kind", "url", "api_key_env", "api_token_env"):
        if key in backend_cfg:
            normalized[key] = deepcopy(backend_cfg[key])
    return normalized
