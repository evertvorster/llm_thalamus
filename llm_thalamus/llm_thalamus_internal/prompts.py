from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from llm_thalamus_internal.config import CallConfig


def load_prompt_template(
    call_name: str,
    call_config: CallConfig,
    base_dir: Path,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Load the prompt template text for a given call from disk, if configured.

    Resolution rules:
    - Use call_config.prompt_file if set.
    - If the path is relative, treat it as relative to base_dir.
    - On any failure, log and return None (callers can fall back to
      inline prompts).
    """
    logger = logger or logging.getLogger("thalamus")

    path_str = call_config.prompt_file
    if not path_str:
        return None

    path = Path(path_str)
    if not path.is_absolute():
        # For now, keep it simple: resolve relative to base_dir.
        path = base_dir / path

    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "Prompt template for call %s not found at %s",
            call_name,
            path,
        )
        return None
    except Exception:
        logger.exception(
            "Error loading prompt template for call %s from %s",
            call_name,
            path,
        )
        return None
