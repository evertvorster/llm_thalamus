from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ._cli import parse_bootstrap_args
from ._load import ensure_config_file_exists, load_raw_config_json
from ._policy import compute_roots_for_mode
from ._rootfind import find_project_root
from ._schema import extract_effective_values


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

    # llm
    llm_provider: str
    llm_model: str
    llm_kind: str
    llm_url: str

    # openmemory
    openmemory_mode: str
    openmemory_tier: str
    openmemory_endpoint_kind: str
    openmemory_endpoint_url: str | None
    openmemory_db_path: Path

    # embeddings
    embeddings_provider: str
    embeddings_model: str
    embeddings_ollama_url: str

    # files
    log_file: Path
    message_file: Path

    # history
    history_message_limit: int
    message_history_max: int

    # resources
    prompt_files: Mapping[str, Path]

    # ui assets
    graphics_dir: Path

    raw: dict


def bootstrap_config(argv: list[str]) -> ConfigSnapshot:
    args = parse_bootstrap_args(argv)
    project_root = find_project_root(Path.cwd())

    mode = "dev" if args.dev_mode else "installed"
    roots = compute_roots_for_mode(mode=mode, project_root=project_root)

    if mode == "installed":
        ensure_config_file_exists(config_file=roots.config_file, config_template=roots.config_template)


    raw = load_raw_config_json(roots.config_file)

    eff = extract_effective_values(
        raw=raw,
        resources_root=roots.resources_root,
        data_root=roots.data_root,
        state_root=roots.state_root,
        project_root=roots.project_root,
        dev_mode=(mode == "dev"),
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
        llm_provider=eff.llm_provider,
        llm_model=eff.llm_model,
        llm_kind=eff.llm_kind,
        llm_url=eff.llm_url,
        openmemory_mode=eff.openmemory_mode,
        openmemory_tier=eff.openmemory_tier,
        openmemory_endpoint_kind=eff.openmemory_endpoint_kind,
        openmemory_endpoint_url=eff.openmemory_endpoint_url,
        openmemory_db_path=eff.openmemory_db_path,
        embeddings_provider=eff.embeddings_provider,
        embeddings_model=eff.embeddings_model,
        embeddings_ollama_url=eff.embeddings_ollama_url,
        log_file=eff.log_file,
        message_file=eff.message_file,
        history_message_limit=eff.history_message_limit,
        message_history_max=eff.message_history_max,
        prompt_files=eff.prompt_files,
        graphics_dir=eff.graphics_dir,
        raw=raw,
    )
