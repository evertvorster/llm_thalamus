from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ._cli import parse_bootstrap_args
from ._load import ensure_config_file_exists, load_raw_config_json
from ._policy import compute_roots_for_mode, format_mode_summary
from ._rootfind import find_project_root
from ._schema import extract_effective_values

__all__ = ["ConfigSnapshot", "bootstrap_config", "compute_mode_summaries"]


@dataclass(frozen=True)
class ConfigSnapshot:
    dev_mode: bool
    project_root: Path
    resources_root: Path

    config_template: Path
    config_file: Path

    runtime_root: Path
    data_root: Path
    state_root: Path

    # thalamus / chat
    llm_model: str

    # openmemory
    openmemory_mode: str
    openmemory_tier: str
    openmemory_endpoint_kind: str
    openmemory_endpoint_url: str | None
    openmemory_db_path: Path

    # openmemory embeddings
    embeddings_provider: str
    embeddings_model: str
    embeddings_ollama_url: str

    # state/log
    log_file: Path
    message_file: Path

    # resources
    prompt_files: Mapping[str, Path]

    # keep the whole original config for forward compatibility
    raw: dict


def bootstrap_config(argv: list[str], *, start_dir: Path | None = None) -> ConfigSnapshot:
    """
    The ONLY API that llm_thalamus.py should call.

    Policy:
      - --dev (or LLM_THALAMUS_DEV=1) selects dev mode.
      - Dev mode uses resources/config/config.json directly as both template + active config.
      - Installed mode:
          template: /usr/share/llm-thalamus/config/config.json
          active:   ~/.config/llm-thalamus/config.json (created from template if missing)
    """
    args = parse_bootstrap_args(argv)

    if start_dir is None:
        start_dir = Path.cwd()

    project_root = find_project_root(start_dir)
    mode = "dev" if args.dev_mode else "installed"

    roots = compute_roots_for_mode(mode=mode, project_root=project_root)

    if mode == "installed":
        ensure_config_file_exists(config_file=roots.config_file, config_template=roots.config_template)

    raw = load_raw_config_json(roots.config_file)

    effective = extract_effective_values(
        raw=raw,
        resources_root=roots.resources_root,
        data_root=roots.data_root,
        state_root=roots.state_root,
    )

    return ConfigSnapshot(
        dev_mode=(mode == "dev"),
        project_root=roots.project_root,
        resources_root=roots.resources_root,
        config_template=roots.config_template,
        config_file=roots.config_file,
        runtime_root=roots.runtime_root,
        data_root=roots.data_root,
        state_root=roots.state_root,
        llm_model=effective.llm_model,
        openmemory_mode=effective.openmemory_mode,
        openmemory_tier=effective.openmemory_tier,
        openmemory_endpoint_kind=effective.openmemory_endpoint_kind,
        openmemory_endpoint_url=effective.openmemory_endpoint_url,
        openmemory_db_path=effective.openmemory_db_path,
        embeddings_provider=effective.embeddings_provider,
        embeddings_model=effective.embeddings_model,
        embeddings_ollama_url=effective.embeddings_ollama_url,
        log_file=effective.log_file,
        message_file=effective.message_file,
        prompt_files=effective.prompt_files,
        raw=raw,
    )


def compute_mode_summaries(argv: list[str], *, start_dir: Path | None = None) -> str:
    """
    Debug helper: show dev vs installed resolved paths with NO side effects.
    Always loads the shipped dev template file (resources/config/config.json) as the raw base.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    project_root = find_project_root(start_dir)

    dev_roots = compute_roots_for_mode(mode="dev", project_root=project_root, create_dirs=False)
    raw = load_raw_config_json(dev_roots.config_file)

    dev_effective = extract_effective_values(
        raw=raw,
        resources_root=dev_roots.resources_root,
        data_root=dev_roots.data_root,
        state_root=dev_roots.state_root,
    )

    inst_roots = compute_roots_for_mode(mode="installed", project_root=project_root, create_dirs=False)
    inst_effective = extract_effective_values(
        raw=raw,
        resources_root=inst_roots.resources_root,
        data_root=inst_roots.data_root,
        state_root=inst_roots.state_root,
    )

    return format_mode_summary(
        dev_roots=dev_roots,
        dev_effective=dev_effective,
        inst_roots=inst_roots,
        inst_effective=inst_effective,
    )
