from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ._policy import resolve_writable_path


@dataclass(frozen=True)
class EffectiveValues:
    # llm / chat
    llm_provider: str
    llm_model: str
    llm_kind: str
    llm_url: str

    # llm / orchestration
    llm_roles: Mapping[str, Mapping[str, Any]]

    # state
    log_file: Path
    message_file: Path

    # chat history limits
    history_message_limit: int
    message_history_max: int

    # orchestrator policy (langgraph-ish)
    orchestrator_tool_step_limit: int
    orchestrator_retrieval_default_k: int
    orchestrator_retrieval_max_k: int
    orchestrator_retrieval_min_score: float
    orchestrator_routing_default_intent: str

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


def _get_float(d: dict, key: str, default: float) -> float:
    try:
        return float(d.get(key, default))
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
    llm = _get_dict(raw, "llm")

    # --- LLM ---
    llm_provider = _get_str(llm, "provider", "").strip()
    llm_model = _get_str(llm, "model", "").strip()

    raw_roles = llm.get("roles", {}) or {}
    if not isinstance(raw_roles, dict):
        raise ValueError("config: llm.roles must be an object")

    llm_roles: dict[str, Mapping[str, Any]] = {}
    for role_name, role_obj in raw_roles.items():
        if not isinstance(role_name, str):
            continue
        if not isinstance(role_obj, dict):
            raise ValueError(f"config: llm.roles.{role_name} must be an object")

        model = role_obj.get("model")
        if model is None:
            raise ValueError(f"config: llm.roles.{role_name}.model is required")
        model = str(model).strip()
        if not model:
            raise ValueError(
                f"config: llm.roles.{role_name}.model must be a non-empty string"
            )

        params = role_obj.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"config: llm.roles.{role_name}.params must be an object")

        response_format = role_obj.get("response_format", None)
        # response_format may be None, "json", "text", or a schema object
        if isinstance(response_format, str):
            response_format = response_format.strip() or None

        llm_roles[role_name] = {
            "model": model,
            "params": params,
            "response_format": response_format,
        }

    # No fallbacks: required roles must exist.
    for required in ("router", "answer", "reflect"):
        if required not in llm_roles:
            raise ValueError(f"config: llm.roles.{required} is required")

    # Hard policy: router + reflect must be explicitly JSON-enforced.
    if (llm_roles["router"].get("response_format") or "").strip() != "json":
        raise ValueError("config: llm.roles.router.response_format must be 'json'")
    if (llm_roles["reflect"].get("response_format") or "").strip() != "json":
        raise ValueError("config: llm.roles.reflect.response_format must be 'json'")

    providers = llm.get("providers", {}) or {}
    provider_cfg = providers.get(llm_provider, {}) or {}

    llm_kind = _get_str(provider_cfg, "kind", llm_provider)
    llm_url = _get_str(provider_cfg, "url", "")

    # --- Files ---
    log_file = resolve_writable_path(
        state_root, _get_str(logging_cfg, "file", "log/thalamus.log")
    )

    message_file = resolve_writable_path(
        data_root, _get_str(thalamus, "message_file", "chat_history.jsonl")
    )

    # --- History limits ---
    stm = thalamus.get("short_term_memory", {}) or {}
    orch = thalamus.get("orchestrator", {}) or {}
    orch_limits = (orch.get("limits", {}) or {}) if isinstance(orch, dict) else {}
    orch_retrieval = (orch.get("retrieval", {}) or {}) if isinstance(orch, dict) else {}
    orch_routing = (orch.get("routing", {}) or {}) if isinstance(orch, dict) else {}

    history_message_limit = _get_int(
        orch_limits,
        "history_message_limit",
        _get_int(thalamus, "history_message_limit", _get_int(stm, "max_messages", 20)),
    )

    message_history_max = _get_int(
        thalamus,
        "message_history_max",
        _get_int(thalamus, "message_history", 100),
    )

    # --- Orchestrator policy ---
    orchestrator_tool_step_limit = _get_int(
        orch_limits,
        "tool_step_limit",
        _get_int(thalamus, "max_tool_steps", 16),
    )

    orchestrator_retrieval_default_k = _get_int(orch_retrieval, "default_k", 10)
    orchestrator_retrieval_max_k = _get_int(
        orch_retrieval,
        "max_k",
        _get_int(thalamus, "max_memory_results", 40),
    )
    orchestrator_retrieval_min_score = _get_float(orch_retrieval, "min_score", 0.0)
    orchestrator_routing_default_intent = _get_str(
        orch_routing,
        "default_intent",
        "qa",
    )

    if orchestrator_retrieval_default_k < 0:
        orchestrator_retrieval_default_k = 0
    if orchestrator_retrieval_max_k < 0:
        orchestrator_retrieval_max_k = 0
    if orchestrator_retrieval_max_k < orchestrator_retrieval_default_k:
        raise ValueError(
            "config: thalamus.orchestrator.retrieval.max_k must be >= default_k"
        )

    if dev_mode:
        graphics_dir = project_root / "resources" / "graphics"
    else:
        graphics_dir = Path("/usr/share/llm-thalamus/graphics")

    return EffectiveValues(
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_kind=llm_kind,
        llm_url=llm_url,
        llm_roles=llm_roles,
        log_file=log_file,
        message_file=message_file,
        history_message_limit=history_message_limit,
        message_history_max=message_history_max,
        orchestrator_tool_step_limit=orchestrator_tool_step_limit,
        orchestrator_retrieval_default_k=orchestrator_retrieval_default_k,
        orchestrator_retrieval_max_k=orchestrator_retrieval_max_k,
        orchestrator_retrieval_min_score=orchestrator_retrieval_min_score,
        orchestrator_routing_default_intent=orchestrator_routing_default_intent,
        graphics_dir=graphics_dir,
    )
