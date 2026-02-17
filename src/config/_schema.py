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
    llm_langgraph_nodes: Mapping[str, str]

    # llm / per-role controls
    llm_role_params: Mapping[str, Mapping[str, Any]]
    llm_role_response_format: Mapping[str, Any]

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

    raw_nodes = llm.get("langgraph_nodes", {}) or {}
    llm_langgraph_nodes: dict[str, str] = {}
    if isinstance(raw_nodes, dict):
        for k, v in raw_nodes.items():
            if not isinstance(k, str):
                continue
            if v is None:
                continue
            llm_langgraph_nodes[k] = str(v).strip()

    if not llm_langgraph_nodes.get("final"):
        raise ValueError("config: llm.langgraph_nodes.final is required")

    # --- LLM per-role controls ---
    raw_role_params = llm.get("role_params", {})
    if not isinstance(raw_role_params, dict):
        raise ValueError("config: llm.role_params must be an object")

    llm_role_params: dict[str, Mapping[str, Any]] = {}
    for k, v in raw_role_params.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, dict):
            raise ValueError(f"config: llm.role_params.{k} must be an object")
        llm_role_params[k] = v

    raw_role_fmt = llm.get("role_response_format", {})
    if not isinstance(raw_role_fmt, dict):
        raise ValueError("config: llm.role_response_format must be an object")

    llm_role_response_format: dict[str, Any] = {}
    for k, v in raw_role_fmt.items():
        if not isinstance(k, str):
            continue
        # v may be None, "json", or a schema object
        llm_role_response_format[k] = v

    # No fallbacks: router must be explicitly JSON-enforced.
    if (llm_role_response_format.get("router") or "").strip() != "json":
        raise ValueError("config: llm.role_response_format.router must be 'json'")

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
        llm_langgraph_nodes=llm_langgraph_nodes,
        llm_role_params=llm_role_params,
        llm_role_response_format=llm_role_response_format,
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
