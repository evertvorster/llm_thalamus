from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


def ensure_config_file_exists(*, config_file: Path, config_template: Path) -> None:
    """
    Ensure the user-owned config_file exists. If missing, copy from config_template.

    This must be called in installed mode before loading config_file.
    """
    if config_file.exists():
        return

    if not config_template.exists():
        raise FileNotFoundError(f"Config template not found: {config_template}")

    config_file.parent.mkdir(parents=True, exist_ok=True)

    # Atomic-ish copy: copy to temp in same dir then replace
    tmp_dir = config_file.parent
    with tempfile.NamedTemporaryFile(prefix=".config.json.", dir=tmp_dir, delete=False) as tf:
        tmp_path = Path(tf.name)

    try:
        shutil.copyfile(config_template, tmp_path)
        tmp_path.replace(config_file)
    finally:
        if tmp_path.exists() and tmp_path != config_file:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def load_raw_config_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
