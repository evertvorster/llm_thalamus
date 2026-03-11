from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


def ensure_json_file_exists(*, file_path: Path, template_path: Path, temp_prefix: str) -> None:
    """
    Ensure the user-owned JSON file exists. If missing, copy from its template.
    """
    if file_path.exists():
        return

    if not template_path.exists():
        raise FileNotFoundError(f"JSON template not found: {template_path}")

    file_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = file_path.parent
    with tempfile.NamedTemporaryFile(prefix=temp_prefix, dir=tmp_dir, delete=False) as tf:
        tmp_path = Path(tf.name)

    try:
        shutil.copyfile(template_path, tmp_path)
        tmp_path.replace(file_path)
    finally:
        if tmp_path.exists() and tmp_path != file_path:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def load_raw_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_raw_json(path: Path, payload: dict, *, temp_prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(prefix=temp_prefix, dir=path.parent, delete=False) as tf:
        tmp_path = Path(tf.name)

    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists() and tmp_path != path:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def ensure_config_file_exists(*, config_file: Path, config_template: Path) -> None:
    ensure_json_file_exists(
        file_path=config_file,
        template_path=config_template,
        temp_prefix=".config.json.",
    )


def load_raw_config_json(path: Path) -> dict:
    return load_raw_json(path)


def save_raw_config_json(path: Path, payload: dict) -> None:
    save_raw_json(path, payload, temp_prefix=".config.json.")
