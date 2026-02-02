# src/llm_thalamus/config/paths.py
from __future__ import annotations

from pathlib import Path
import os
import shutil


# ---------------------------
# Mode / identity
# ---------------------------

def is_dev_mode() -> bool:
    """
    Explicit dev-mode toggle.

    Dev mode exists to allow running an installed instance and a development
    instance simultaneously without colliding on config/data/log locations.
    """
    v = os.environ.get("LLM_THALAMUS_DEV", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def app_id() -> str:
    """
    Instance identifier used to namespace XDG directories and repo-local scratch.

    - installed: "llm-thalamus"
    - dev:       "llm-thalamus-dev" (optionally + "-<instance>")
    """
    base = "llm-thalamus"
    if not is_dev_mode():
        return base

    inst = os.environ.get("LLM_THALAMUS_INSTANCE", "").strip()
    if inst:
        return f"{base}-dev-{inst}"
    return f"{base}-dev"


# ---------------------------
# Repo + resources
# ---------------------------

def repo_root() -> Path:
    """
    Repo root resolution (only meaningful in dev mode).

    Expected layout:
      <repo>/src/llm_thalamus/config/paths.py
      <repo>/resources/...
      <repo>/var/...   (dev scratch default)
    """
    # paths.py -> config -> llm_thalamus -> src -> repo
    return Path(__file__).resolve().parents[3]


def resources_root() -> Path:
    """
    Option A resources policy:

    1) Explicit override: LLM_THALAMUS_RESOURCES_DIR
    2) Dev: <repo>/resources
    3) Installed: /usr/share/llm-thalamus
       (expects subdirs like ui/, prompts/, config/)
    """
    override = os.environ.get("LLM_THALAMUS_RESOURCES_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if is_dev_mode():
        return (repo_root() / "resources").resolve()

    return Path("/usr/share/llm-thalamus")


def resource_path(rel: str) -> Path:
    """
    Resolve a resource within the resources root.

    Example:
      resource_path("ui/icons/brain.svg")
      resource_path("prompts/answer.txt")
      resource_path("config/default.json")
    """
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return rel_path.expanduser().resolve()
    return (resources_root() / rel_path).resolve()


# ---------------------------
# Runtime roots (config/data/state/logs)
# ---------------------------

def _runtime_root_override() -> Path | None:
    """
    If set, a single root under which we create:
      <root>/config/config.json
      <root>/data/...
      <root>/state/logs/...
    """
    v = os.environ.get("LLM_THALAMUS_RUNTIME_DIR", "").strip()
    if not v:
        return None
    return Path(v).expanduser().resolve()


def _dev_runtime_root_default() -> Path:
    """
    Default dev scratch root:
      <repo>/var/<app_id>/

    This lives next to resources, not inside src, so code dumps remain clean.
    """
    return (repo_root() / "var" / app_id()).resolve()


def config_dir() -> Path:
    """
    Directory containing config.json.

    - If LLM_THALAMUS_RUNTIME_DIR is set: <runtime>/config
    - Dev: <repo>/var/<app_id>/config
    - Installed: ${XDG_CONFIG_HOME}/<app_id>
    """
    rt = _runtime_root_override()
    if rt is not None:
        d = rt / "config"
    elif is_dev_mode():
        d = _dev_runtime_root_default() / "config"
    else:
        cfg_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        d = cfg_home / app_id()

    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    """
    Path to the active config.json.

    If missing, it is created on first run from a template:
      1) resources/config/default.json
      2) /etc/llm-thalamus/config.json  (fallback)
    """
    override = os.environ.get("LLM_THALAMUS_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    cfg = config_dir() / "config.json"
    if not cfg.exists():
        _ensure_default_config(cfg)
    return cfg


def data_root() -> Path:
    """
    Root for runtime data (DBs, caches that are not state/logs).

    - If LLM_THALAMUS_RUNTIME_DIR is set: <runtime>/data
    - Dev: <repo>/var/<app_id>/data
    - Installed: ${XDG_DATA_HOME}/<app_id>
    """
    rt = _runtime_root_override()
    if rt is not None:
        d = rt / "data"
    elif is_dev_mode():
        d = _dev_runtime_root_default() / "data"
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        d = data_home / app_id()

    d.mkdir(parents=True, exist_ok=True)
    return d


def state_root() -> Path:
    """
    Root for runtime state (logs, transient state, pid files, etc.).

    - If LLM_THALAMUS_RUNTIME_DIR is set: <runtime>/state
    - Dev: <repo>/var/<app_id>/state
    - Installed: ${XDG_STATE_HOME}/<app_id>
    """
    rt = _runtime_root_override()
    if rt is not None:
        d = rt / "state"
    elif is_dev_mode():
        d = _dev_runtime_root_default() / "state"
    else:
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        d = state_home / app_id()

    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = state_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_history_dir() -> Path:
    d = data_root() / "chat_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_runtime_dirs() -> None:
    """
    Convenience: ensure all runtime dirs exist.
    """
    _ = config_dir()
    _ = data_root()
    _ = state_root()
    _ = logs_dir()
    _ = chat_history_dir()


# ---------------------------
# Deterministic path resolution
# ---------------------------

def resolve_app_path(p: str, *, kind: str) -> Path:
    """
    Resolve a path from config.json deterministically.

    - Absolute paths: returned as-is (with ~ expanded).
    - Relative paths: anchored to app-controlled roots (NOT CWD).

    kind:
      - "data": DBs and other persistent runtime data
      - "log":  log files (under state/logs)
      - "state": other state files (under state/)
      - any other value falls back to data_root anchoring

    Backward-compatible shims:
      - "./data/..." -> data_root()/data/...
      - "./log/..."  -> logs_dir()/...
    """
    raw = Path(p).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    # Strip leading "./"
    s = p[2:] if p.startswith("./") else p

    # Back-compat for old defaults: they used "data/" and "log/" prefixes.
    if kind == "data":
        if s.startswith("data/"):
            s = s[len("data/"):]
        return (data_root() / "data" / s).resolve()

    if kind == "log":
        if s.startswith("log/"):
            s = s[len("log/"):]
        if s.startswith("logs/"):
            s = s[len("logs/"):]
        return (logs_dir() / s).resolve()

    if kind == "state":
        return (state_root() / s).resolve()

    return (data_root() / s).resolve()


# ---------------------------
# Config template creation
# ---------------------------

def _ensure_default_config(dst: Path) -> None:
    """
    Create a config.json at dst by copying from a template.
    """
    # Primary template (your new policy)
    template = resource_path("config/default.json")
    if template.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, dst)
        return

    # Fallback for systems that still ship /etc/llm-thalamus/config.json
    system_cfg = Path("/etc/llm-thalamus/config.json")
    if system_cfg.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(system_cfg, dst)
        return

    raise FileNotFoundError(
        f"Missing config template. Expected {template} or {system_cfg}."
    )


# ---------------------------
# UI assets compatibility
# ---------------------------

def get_images_dir() -> Path:
    """
    Compatibility helper for UI assets directory.

    New policy prefers:
      resources/ui/

    Legacy fallbacks (for old layouts):
      resources/graphics/, resources/images/
      /usr/share/llm-thalamus/graphics, /usr/share/llm-thalamus/images
    """
    root = resources_root()

    for sub in ("ui", "graphics", "images"):
        p = (root / sub).resolve()
        if p.exists():
            return p

    # Return the preferred location even if it doesn't exist yet (callers can decide).
    return (root / "ui").resolve()
