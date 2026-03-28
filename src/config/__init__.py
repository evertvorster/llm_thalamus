from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from controller.internal_tools.config import load_internal_tools_config
from controller.mcp.config import load_mcp_config
from .llm_backends import load_llm_backends_config

from ._cli import parse_bootstrap_args
from ._load import ensure_config_file_exists, ensure_json_file_exists, load_raw_config_json
from ._policy import compute_roots_for_mode
from ._rootfind import find_project_root
from ._schema import extract_effective_values


def _migrate_legacy_llm_providers(*, raw: dict, llm_backends: dict) -> dict:
    if not isinstance(raw, dict):
        return llm_backends
    llm_cfg = raw.get("llm")
    if not isinstance(llm_cfg, dict):
        return llm_backends
    legacy_providers = llm_cfg.get("providers")
    if not isinstance(legacy_providers, dict):
        return llm_backends

    out = json.loads(json.dumps(llm_backends if isinstance(llm_backends, dict) else {}))
    backends = out.get("backends")
    if not isinstance(backends, dict):
        backends = {}
        out["backends"] = backends

    for key, value in legacy_providers.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if key not in backends:
            backends[key] = dict(value)
    return out


@dataclass(frozen=True)
class ConfigSnapshot:
    dev_mode: bool
    project_root: Path
    resources_root: Path
    config_template: Path
    config_file: Path
    llm_backends_template: Path
    llm_backends_file: Path
    mcp_servers_template: Path
    mcp_servers_file: Path
    internal_tools_template: Path
    internal_tools_file: Path
    runtime_root: Path
    data_root: Path
    state_root: Path

    # llm
    llm_provider: str
    llm_kind: str
    llm_url: str
    llm_roles: Mapping[str, Mapping[str, Any]]

    llm_backends: Mapping[str, Any]
    mcp_servers: Mapping[str, Any]
    internal_tools: Mapping[str, Any]

    # files
    log_file: Path
    message_file: Path

    # history
    history_message_limit: int
    message_history_max: int

    # orchestrator policy
    orchestrator_tool_step_limit: int
    orchestrator_retrieval_default_k: int
    orchestrator_retrieval_max_k: int
    orchestrator_retrieval_min_score: float
    orchestrator_routing_default_intent: str
    orchestrator_prefill_shared_k: int
    orchestrator_prefill_user_k: int
    orchestrator_prefill_agent_k: int

    # ui assets
    graphics_dir: Path

    raw: dict


def bootstrap_config(argv: list[str]) -> ConfigSnapshot:
    args = parse_bootstrap_args(argv)
    project_root = find_project_root(Path.cwd())

    mode = "dev" if args.dev_mode else "installed"
    roots = compute_roots_for_mode(mode=mode, project_root=project_root)

    if mode == "installed":
        ensure_config_file_exists(
            config_file=roots.config_file, config_template=roots.config_template
        )
        ensure_config_file_exists(
            config_file=roots.llm_backends_file,
            config_template=roots.llm_backends_template,
        )
        ensure_config_file_exists(
            config_file=roots.mcp_servers_file,
            config_template=roots.mcp_servers_template,
        )
        ensure_json_file_exists(
            file_path=roots.internal_tools_file,
            template_path=roots.internal_tools_template,
            temp_prefix=".internal_tools.json.",
        )

    raw = load_raw_config_json(roots.config_file)
    llm_backends = _migrate_legacy_llm_providers(
        raw=raw,
        llm_backends=load_llm_backends_config(roots.llm_backends_file),
    )
    mcp_servers = load_mcp_config(roots.mcp_servers_file)
    internal_tools = load_internal_tools_config(roots.internal_tools_file)

    eff = extract_effective_values(
        raw=raw,
        llm_backends=llm_backends,
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
        llm_backends_template=roots.llm_backends_template,
        llm_backends_file=roots.llm_backends_file,
        mcp_servers_template=roots.mcp_servers_template,
        mcp_servers_file=roots.mcp_servers_file,
        internal_tools_template=roots.internal_tools_template,
        internal_tools_file=roots.internal_tools_file,
        runtime_root=roots.runtime_root,
        data_root=roots.data_root,
        state_root=roots.state_root,
        llm_provider=eff.llm_provider,
        llm_kind=eff.llm_kind,
        llm_url=eff.llm_url,
        llm_roles=eff.llm_roles,
        llm_backends=llm_backends,
        mcp_servers=mcp_servers,
        internal_tools=internal_tools,
        log_file=eff.log_file,
        message_file=eff.message_file,
        history_message_limit=eff.history_message_limit,
        message_history_max=eff.message_history_max,
        orchestrator_tool_step_limit=eff.orchestrator_tool_step_limit,
        orchestrator_retrieval_default_k=eff.orchestrator_retrieval_default_k,
        orchestrator_retrieval_max_k=eff.orchestrator_retrieval_max_k,
        orchestrator_retrieval_min_score=eff.orchestrator_retrieval_min_score,
        orchestrator_routing_default_intent=eff.orchestrator_routing_default_intent,
        orchestrator_prefill_shared_k=eff.orchestrator_prefill_shared_k,
        orchestrator_prefill_user_k=eff.orchestrator_prefill_user_k,
        orchestrator_prefill_agent_k=eff.orchestrator_prefill_agent_k,
        graphics_dir=eff.graphics_dir,
        raw=raw,
    )
