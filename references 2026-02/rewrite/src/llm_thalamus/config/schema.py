from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from llm_thalamus.config import paths


@dataclass
class CallConfig:
    """
    Per-LLM-call configuration.
    Mirrors old llm_thalamus_internal.config.CallConfig.
    """
    prompt_file: Optional[str] = None
    max_memories: Optional[int] = None
    max_messages: Optional[int] = None
    memory_limits_by_sector: Optional[Dict[str, int]] = None
    use_memories: bool = True
    use_history: bool = True
    use_documents: bool = True
    flags: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclass
class OpenMemoryConfig:
    """
    OpenMemory connection/config.
    - db_path is stored raw (as in config.json), but resolution is handled via paths.resolve_app_path()
    """
    db_path: str = "./data/memory.sqlite"
    tier: Optional[str] = "smart"
    ollama_model: Optional[str] = None
    backend_url: Optional[str] = None

    def db_path_resolved(self) -> Path:
        return paths.resolve_app_path(self.db_path, kind="data")


@dataclass
class ThalamusConfig:
    project_name: str = "llm-thalamus"
    default_user_id: str = "default"

    # LLM / Ollama
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"

    # Embeddings provider/model (used by OpenMemory adapters and validation)
    embeddings_provider: str = "ollama"
    embeddings_model: Optional[str] = "nomic-embed-text:latest"

    # OpenMemory
    openmemory: OpenMemoryConfig = dataclasses.field(default_factory=OpenMemoryConfig)

    # Memory behaviour
    max_memory_results: int = 20
    enable_reflection: bool = True

    # Short-term conversation context (in-RAM rolling window)
    short_term_max_messages: int = 0  # 0 = disabled

    # On-disk JSONL chat history (message history subsystem)
    message_history_max: int = 100  # 0 = disabled
    message_file: str = "chat_history.jsonl"

    # Agent / tools behaviour
    tools: Dict[str, dict] = dataclasses.field(default_factory=dict)
    max_tool_steps: int = 16

    # Per-call configuration
    calls: Dict[str, CallConfig] = dataclasses.field(default_factory=dict)

    # Logging
    log_level: str = "INFO"
    log_file: Path = dataclasses.field(default_factory=lambda: paths.logs_dir() / "thalamus.log")

    def openmemory_db_path(self) -> Path:
        return self.openmemory.db_path_resolved()

    def openmemory_db_url(self) -> str:
        # openmemory-py expects sqlite URLs of the form:
        #   sqlite:////absolute/path/to/db.sqlite
        db_path = self.openmemory_db_path()
        return f"sqlite:////{str(db_path).lstrip('/')}"


# ---------------------------
# Parsing helpers (raw dict -> typed)
# ---------------------------

def parse_calls(raw: Dict[str, Any]) -> Dict[str, CallConfig]:
    """
    Parse per-call configs from raw JSON.

    - raw['calls'] expected to be: { call_name: { ...call config... } }
    """
    calls_raw = raw.get("calls", {})
    if not isinstance(calls_raw, dict):
        return {}

    out: Dict[str, CallConfig] = {}
    for call_name, call_cfg in calls_raw.items():
        if not isinstance(call_name, str) or not isinstance(call_cfg, dict):
            continue

        out[call_name] = _parse_call_config(call_cfg)

    return out


def _parse_call_config(merged: Dict[str, Any]) -> CallConfig:
    mem_limits = merged.get("memory_limits_by_sector")
    if not isinstance(mem_limits, dict):
        mem_limits = None
    else:
        # normalize to {str:int}
        norm: Dict[str, int] = {}
        for k, v in mem_limits.items():
            if isinstance(k, str):
                try:
                    norm[k] = int(v)
                except Exception:
                    continue
        mem_limits = norm

    return CallConfig(
        prompt_file=merged.get("prompt_file"),
        max_memories=merged.get("max_memories"),
        max_messages=merged.get("max_messages"),
        memory_limits_by_sector=mem_limits,
        use_memories=bool(merged.get("use_memories", True)),
        use_history=bool(merged.get("use_history", True)),
        use_documents=bool(merged.get("use_documents", True)),
        flags=dict(merged.get("flags") or {}),
    )


def parse_thalamus_config(raw: Dict[str, Any]) -> ThalamusConfig:
    """
    Mechanical port of ThalamusConfig.load() parsing logic.
    This does NOT decide where the file lives; loader.py does that.
    """
    th_cfg = raw.get("thalamus", {}) if isinstance(raw.get("thalamus"), dict) else {}
    emb_cfg = raw.get("embeddings", {}) if isinstance(raw.get("embeddings"), dict) else {}
    logging_cfg = raw.get("logging", {}) if isinstance(raw.get("logging"), dict) else {}
    tools_cfg = raw.get("tools", {}) if isinstance(raw.get("tools"), dict) else {}
    om_cfg = raw.get("openmemory", {}) if isinstance(raw.get("openmemory"), dict) else {}

    short_term_cfg = th_cfg.get("short_term_memory", {}) if isinstance(th_cfg.get("short_term_memory"), dict) else {}
    short_term_max_messages = int(short_term_cfg.get("max_messages", 0) or 0)

    # Logging file: use config value if present; otherwise use paths.logs_dir()
    log_file_raw = logging_cfg.get("file")
    log_file = (
        Path(str(log_file_raw))
        if isinstance(log_file_raw, str) and log_file_raw.strip()
        else (paths.logs_dir() / "thalamus.log")
    )

    # Per-call configuration
    calls = parse_calls(raw)

    # Tools section
    tools: Dict[str, dict] = tools_cfg if isinstance(tools_cfg, dict) else {}

    # OpenMemory section (raw path preserved; resolved via methods)
    om_path = om_cfg.get("path")
    if not isinstance(om_path, str) or not om_path.strip():
        om_path = "./data/memory.sqlite"

    backend_url = om_cfg.get("backend_url")
    backend_url_norm: Optional[str]
    if isinstance(backend_url, str) and backend_url.strip():
        backend_url_norm = backend_url.rstrip("/")
    else:
        backend_url_norm = None

    openmemory = OpenMemoryConfig(
        db_path=str(om_path).strip(),
        tier=om_cfg.get("tier"),
        ollama_model=om_cfg.get("ollama_model"),
        backend_url=backend_url_norm,
    )

    return ThalamusConfig(
        project_name=th_cfg.get("project_name", "llm-thalamus"),
        default_user_id=th_cfg.get("default_user_id", "default"),
        ollama_url=emb_cfg.get("ollama_url", "http://localhost:11434"),
        llm_model=th_cfg.get("llm_model", "qwen2.5:7b"),
        embeddings_provider=emb_cfg.get("provider", "ollama"),
        embeddings_model=emb_cfg.get("model"),
        openmemory=openmemory,
        max_memory_results=int(th_cfg.get("max_memory_results", 20) or 0),
        enable_reflection=bool(th_cfg.get("enable_reflection", True)),
        short_term_max_messages=short_term_max_messages,
        message_history_max=int(th_cfg.get("message_history", 100) or 0),
        message_file=str(th_cfg.get("message_file", "chat_history.jsonl")),
        tools=tools,
        max_tool_steps=int(th_cfg.get("max_tool_steps", 16) or 0),
        calls=calls,
        log_level=logging_cfg.get("level", "INFO"),
        log_file=log_file,
    )
