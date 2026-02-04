from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ._policy import resolve_resource_path, resolve_writable_path


@dataclass(frozen=True)
class EffectiveValues:
    # thalamus / chat config (still unchanged in your file)
    llm_model: str

    # openmemory core
    openmemory_mode: str
    openmemory_tier: str
    openmemory_endpoint_kind: str
    openmemory_endpoint_url: str | None

    # openmemory storage (writable; used when endpoint_kind == "local")
    openmemory_db_path: Path

    # openmemory embeddings (owned by openmemory now)
    embeddings_provider: str
    embeddings_model: str
    embeddings_ollama_url: str

    # logging / message state (writable)
    log_file: Path
    message_file: Path

    # resources
    prompt_files: Mapping[str, Path]


def _get_dict(raw: dict, key: str) -> dict:
    v = raw.get(key, {})
    return v if isinstance(v, dict) else {}


def _get_str(d: dict, key: str, default: str = "") -> str:
    v = d.get(key, default)
    if v is None:
        return default
    return str(v)


def _get_opt_str(d: dict, key: str) -> str | None:
    v = d.get(key, None)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def extract_effective_values(
    *,
    raw: dict,
    resources_root: Path,
    data_root: Path,
    state_root: Path,
) -> EffectiveValues:
    thalamus = _get_dict(raw, "thalamus")
    logging_cfg = _get_dict(raw, "logging")
    openmemory = _get_dict(raw, "openmemory")

    llm_model = _get_str(thalamus, "llm_model", "")

    # --- openmemory core ---
    openmemory_mode = _get_str(openmemory, "mode", "local")
    openmemory_tier = _get_str(openmemory, "tier", "")

    endpoint = openmemory.get("endpoint", {})
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    openmemory_endpoint_kind = _get_str(endpoint, "kind", "local")
    openmemory_endpoint_url = _get_opt_str(endpoint, "url")

    # --- openmemory storage (writable) ---
    # Only meaningful when endpoint_kind == "local", but always resolve so it’s available.
    om_path = _get_str(openmemory, "path", "./memory.sqlite")
    openmemory_db_path = resolve_writable_path(data_root, om_path)

    # --- openmemory embeddings ---
    embeddings = openmemory.get("embeddings", {})
    embeddings = embeddings if isinstance(embeddings, dict) else {}

    embeddings_provider = _get_str(embeddings, "provider", "")
    embeddings_model = _get_str(embeddings, "model", "")
    embeddings_ollama_url = _get_str(embeddings, "ollama_url", "")

    # --- logging file (writable) ---
    log_path = _get_str(logging_cfg, "file", "./log/thalamus.log")
    log_file = resolve_writable_path(state_root, log_path)

    # --- message file (writable) ---
    msg_path = _get_str(thalamus, "message_file", "chat_history.jsonl")
    message_file = resolve_writable_path(data_root, msg_path)

    # --- prompt files (resources) ---
    prompt_files: dict[str, Path] = {}
    calls = thalamus.get("calls", {}) or {}
    if isinstance(calls, dict):
        for call_name, call_cfg in calls.items():
            if not isinstance(call_cfg, dict):
                continue
            pf = call_cfg.get("prompt_file")
            if pf:
                prompt_files[str(call_name)] = resolve_resource_path(resources_root, str(pf))

    return EffectiveValues(
        llm_model=llm_model,
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
        prompt_files=prompt_files,
    )
