from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from llm_thalamus.config import loader
from llm_thalamus.config.schema import ThalamusConfig


_cached_raw: Optional[Dict[str, Any]] = None
_cached_typed: Optional[ThalamusConfig] = None
_cached_path: Optional[Path] = None


def invalidate_cache() -> None:
    global _cached_raw, _cached_typed, _cached_path
    _cached_raw = None
    _cached_typed = None
    _cached_path = None


def get_raw_config(explicit_path: Optional[Path] = None) -> Dict[str, Any]:
    global _cached_raw, _cached_path
    p = explicit_path
    if p is not None and _cached_path is not None and p != _cached_path:
        invalidate_cache()

    if _cached_raw is None:
        _cached_raw = loader.load_raw_config(explicit_path)
        _cached_path = explicit_path
    return _cached_raw


def get_config(explicit_path: Optional[Path] = None) -> ThalamusConfig:
    global _cached_typed, _cached_path
    p = explicit_path
    if p is not None and _cached_path is not None and p != _cached_path:
        invalidate_cache()

    if _cached_typed is None:
        _cached_typed = loader.load_typed_config(explicit_path)
        _cached_path = explicit_path
    return _cached_typed


def save_config_dict(data: Dict[str, Any], explicit_path: Optional[Path] = None) -> None:
    loader.save_raw_config(data, explicit_path)
    invalidate_cache()


def update_section(section: str, updates: Dict[str, Any], explicit_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    UI-friendly helper:
      - loads raw dict
      - ensures section is a dict
      - overlays updates
      - saves stably and atomically
    """
    cfg = get_raw_config(explicit_path)
    sec = cfg.get(section)
    if not isinstance(sec, dict):
        sec = {}
        cfg[section] = sec

    for k, v in updates.items():
        sec[k] = v

    save_config_dict(cfg, explicit_path)
    return cfg
