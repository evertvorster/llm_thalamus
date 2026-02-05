from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ._policy import resolve_resource_path, resolve_writable_path


@dataclass(frozen=True)
class EffectiveValues:
    # llm / chat
    llm_provider: str
    llm_model: str
    llm_kind: str
    llm_url: str

    # llm / orchestration
    llm_langgraph_nodes: Mapping[str, str]

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

    # state
    log_file: Path
    message_file: Path

    # chat history limits
    history_message_limit: int
    message_history_max: int

    # resources
    prompt_files: Mapping[str, Path]

    # ui assets
    graphics_dir: Path


def _get_dict(raw: dict, key: str) -> dict:
    v = raw.get(key, {})
    return v if isinstance(v, dict) else {}


def _get_str(d: dict, key: str, default: str = "") -> str:
    v = d.get(key, default)
    return default if v is None else str(v)


def _get_int(d: dict, key: str, default: int) -> int:
    try:
        return int(d.get(key, default))
    except Exception:
        return default


def extract_effective_values(
    *,
    raw: dict,
    resources_root: Path,
    data_root: Path,
    state_root: Path,
    project_root: Path,
    dev_mode: bool,
) -> EffectiveValues:
    thalamus = _get_dict(raw, "thalamus")
    logging_cfg = _get_dict(raw, "logging")
    openmemory = _get_dict(raw, "openmemory")
    llm = _get_dict(raw, "llm")

    # --- LLM ---
    llm_provider = _get_str(llm, "provider", "").strip()
    llm_model = _get_str(llm, "model", "").strip()

    # NEW: langgraph nodes (role -> model)
    raw_nodes = llm.get("langgraph_nodes", {}) or {}
    llm_langgraph_nodes: dict[str, str] = {}
    if isinstance(raw_nodes, dict):
        for k, v in raw_nodes.items():
            if isinstance(k, str) and v is not None:
                llm_langgraph_nodes[k] = str(v)

    providers = llm.get("providers", {}) or {}
    provider_cfg = providers.get(llm_provider, {}) or {}

    llm_kind = _get_str(provider_cfg, "kind", llm_provider)
    llm_url = _get_str(provider_cfg, "url", "")

    # --- OpenMemory ---
    openmemory_mode = _get_str(openmemory, "mode", "local")
    openmemory_tier = _get_str(openmemory, "tier", "")

    endpoint = openmemory.get("endpoint", {}) or {}
    openmemory_endpoint_kind = _get_str(endpoint, "kind", "local")
    openmemory_endpoint_url = endpoint.get("url")

    openmemory_db_path = resolve_writable_path(
        data_root, _get_str(openmemory, "path", "memory.sqlite")
    )

    embeddings = openmemory.get("embeddings", {}) or {}
    embeddings_provider = _get_str(embeddings, "provider", "")
    embeddings_model = _get_str(embeddings, "model", "")
    embeddings_ollama_url = _get_str(embeddings, "ollama_url", "")

    # --- Files ---
    log_file = resolve_writable_path(
        state_root, _get_str(logging_cfg, "file", "log/thalamus.log")
    )

    message_file = resolve_writable_path(
        data_root, _get_str(thalamus, "message_file", "chat_history.jsonl")
    )

    # --- History limits ---
    stm = thalamus.get("short_term_memory", {}) or {}

    history_message_limit = _get_int(
        thalamus,
        "history_message_limit",
        _get_int(stm, "max_messages", 20),
    )

    message_history_max = _get_int(
        thalamus,
        "message_history_max",
        _get_int(thalamus, "message_history", 100),
    )

    # --- Prompts ---
    prompt_files: dict[str, Path] = {}
    calls = thalamus.get("calls", {}) or {}
    for name, cfg in calls.items():
        pf = (cfg or {}).get("prompt_file")
        if pf:
            prompt_files[name] = resolve_resource_path(resources_root, pf)

    # --- Graphics / UI assets ---
    if dev_mode:
        graphics_dir = project_root / "resources" / "graphics"
    else:
        graphics_dir = Path("/usr/share/llm-thalamus/graphics")

    return EffectiveValues(
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_kind=llm_kind,
        llm_url=llm_url,
        llm_langgraph_nodes=llm_langgraph_nodes,
        openmemory_mode=openmemory_mode,
        openmemory_tier=openmemory_tier,
        openmemory_endpoint_kind=openmemory_endpoint_kind,
        openmemory_endpoint_url=openmemory_endpoint_url,
        openmemory_db_path=openmemory_db_path,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        embeddings_ollama_url=embeddings_ollama_url,
        log_file=log_file,
        message_file=message_file,
        history_message_limit=history_message_limit,
        message_history_max=message_history_max,
        prompt_files=prompt_files,
        graphics_dir=graphics_dir,
    )
