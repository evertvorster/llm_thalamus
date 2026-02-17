from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from llm_thalamus.config import paths
from llm_thalamus.config.schema import ThalamusConfig, parse_thalamus_config


# ---------------------------
# Template location
# ---------------------------

def get_system_config_template_path() -> Path:
    """
    Option A:
      - Installed: /etc/llm-thalamus/config.json (preferred)
      - Otherwise: resources/config/default.json
    """
    system_cfg = Path("/etc/llm-thalamus/config.json")
    if system_cfg.exists():
        return system_cfg
    return paths.resource_path("config/default.json")


# ---------------------------
# Raw JSON load/save (stable, atomic)
# ---------------------------

def try_load_raw_config(explicit_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = explicit_path or paths.config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_raw_config(explicit_path: Optional[Path] = None) -> Dict[str, Any]:
    return try_load_raw_config(explicit_path) or {}


def save_raw_config(data: Dict[str, Any], explicit_path: Optional[Path] = None) -> None:
    """
    Stable JSON writes:
      - indent=2
      - ensure_ascii=False
      - sort_keys=True (deterministic diffs)
      - newline terminated
      - atomic temp -> replace
    """
    path = explicit_path or paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


# ---------------------------
# Template merge / schema-constrained overlay
# ---------------------------

def overlay_known_keys(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """
    Overlay src values into dst, but only for keys that already exist in dst.
    Mechanical port of the old function.
    """
    for k, dst_v in list(dst.items()):
        if k not in src:
            continue
        src_v = src[k]

        if isinstance(dst_v, dict) and isinstance(src_v, dict):
            dst[k] = overlay_known_keys(dst_v, src_v)
            continue

        # only allow same-type or None
        if dst_v is None or src_v is None or isinstance(src_v, type(dst_v)):
            dst[k] = src_v

    return dst


def merge_user_config_with_template(*, user_cfg: Dict[str, Any], template_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge/upgrade a user config against a template schema.
    Preserves template's config_version if present.
    """
    merged = json.loads(json.dumps(template_cfg))  # deep copy
    merged = overlay_known_keys(merged, user_cfg or {})
    if "config_version" in template_cfg:
        merged["config_version"] = template_cfg.get("config_version")
    return merged


def ensure_config_exists() -> Path:
    """
    Ensure user config exists; if not, create it from a template.
    This relies on paths.config_path() which already creates parent dirs.
    """
    cfg_path = paths.config_path()
    if cfg_path.exists():
        return cfg_path

    template = get_system_config_template_path()
    if not template.exists():
        raise FileNotFoundError(f"Missing config template: {template}")

    raw = json.loads(template.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Template config is not a JSON object: {template}")

    save_raw_config(raw, explicit_path=cfg_path)
    return cfg_path


# ---------------------------
# Migration hook (schema-driven, in-memory)
# ---------------------------

def migrate_in_memory(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder for schema-driven migrations.
    For extraction phase: no semantic changes; only ensure dict-ness.
    """
    return raw if isinstance(raw, dict) else {}


# ---------------------------
# Typed config
# ---------------------------

def load_typed_config(explicit_path: Optional[Path] = None) -> ThalamusConfig:
    """
    Load raw JSON dict and parse into schema.ThalamusConfig.
    If missing/unreadable, returns defaults.
    """
    raw = try_load_raw_config(explicit_path) or {}
    raw = migrate_in_memory(raw)
    try:
        return parse_thalamus_config(raw)
    except Exception:
        # Extraction-phase behavior: never crash on config parse.
        return ThalamusConfig()
