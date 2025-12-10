# paths.py
from pathlib import Path
import os
import shutil

BASE_DIR = Path(__file__).resolve().parent


def is_dev_mode() -> bool:
    """
    Heuristic: we're in the git checkout if config/ and llm_thalamus.py
    exist next to this file.
    """
    return (BASE_DIR / "config" / "config.json").exists() and \
           (BASE_DIR / "llm_thalamus.py").exists()


# ---------- config ----------

def get_user_config_path() -> Path:
    """
    Dev:  ./config/config.json
    Installed: ~/.config/llm-thalamus/config.json
              (copied from /etc/llm-thalamus/config.json on first run)
    """
    if is_dev_mode():
        return BASE_DIR / "config" / "config.json"

    cfg_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    cfg_dir = cfg_home / "llm-thalamus"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    user_cfg = cfg_dir / "config.json"

    if not user_cfg.exists():
        # system template
        system_cfg = Path("/etc/llm-thalamus/config.json")
        if not system_cfg.exists():
            # fallback to bundled example in site-packages if you ship one
            system_cfg = BASE_DIR / "config" / "config.json"
        shutil.copy2(system_cfg, user_cfg)

    return user_cfg


# ---------- data / logs / chat ----------

def _data_root() -> Path:
    if is_dev_mode():
        root = BASE_DIR
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME",
                                        Path.home() / ".local" / "share"))
        root = data_home / "llm-thalamus"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_chat_history_dir() -> Path:
    if is_dev_mode():
        d = BASE_DIR / "chat_history"
    else:
        d = _data_root() / "chat_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    if is_dev_mode():
        d = BASE_DIR / "log"
    else:
        d = _data_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_data_dir() -> Path:
    if is_dev_mode():
        d = BASE_DIR / "data"
    else:
        d = _data_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- images (for the brain icon later) ----------

def get_images_dir() -> Path:
    if is_dev_mode():
        return BASE_DIR / "images"
    return Path("/usr/share/llm-thalamus/images")
