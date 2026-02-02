from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from llm_thalamus.config.schema import CallConfig
from llm_thalamus.config.paths import resources_root


def load_prompt_template(
    call_name: str,
    call_config: CallConfig,
    base_dir: Optional[Path] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Load the prompt template text for a given call from disk, if configured.

    Resolution rules:
    - Uses call_config.prompt_file if set.
    - If prompt_file is relative, it is resolved relative to base_dir.
      Default base_dir is resources_root().
    - On any failure, logs and returns None.
    """
    logger = logger or logging.getLogger("thalamus")
    base_dir = base_dir or resources_root()

    path_str = call_config.prompt_file
    if not path_str:
        return None

    path = Path(path_str)
    if not path.is_absolute():
        path = base_dir / path

    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Prompt template for call %s not found at %s", call_name, path)
        return None
    except Exception:
        logger.exception("Error loading prompt template for call %s from %s", call_name, path)
        return None
