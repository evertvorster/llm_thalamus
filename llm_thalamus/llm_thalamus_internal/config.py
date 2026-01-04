#!/usr/bin/env python3
"""
llm_thalamus_internal.config

Configuration dataclasses and loader for llm-thalamus.

Phase 1 (central config authority):
- Add OpenMemory configuration (path/tier/model) with deterministic path resolution
  via paths.resolve_app_path(..., kind="data").
- Add embeddings provider/model fields used by OpenMemory integration.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, Optional

from paths import get_user_config_path, get_log_dir, resolve_app_path

# Project root (same directory as llm_thalamus.py)
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Raw JSON config helpers (UI + other modules should use these, not json.load)
# ---------------------------------------------------------------------------

def get_default_config_path() -> Path:
    """Return the resolved user config.json path."""
    return get_user_config_path()


def get_system_config_template_path() -> Path:
    """Return the system (or bundled) config template path.

    Installed: /etc/llm-thalamus/config.json (preferred)
    Dev / fallback: BASE_DIR/config/config.json
    """
    system_cfg = Path("/etc/llm-thalamus/config.json")
    if system_cfg.exists():
        return system_cfg
    return BASE_DIR / "config" / "config.json"


def try_load_raw_config(explicit_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Best-effort JSON load. Returns None on missing/unreadable."""
    path = explicit_path or get_user_config_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_raw_config(explicit_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load raw JSON config as a dict. Returns {} when missing/unreadable."""
    return try_load_raw_config(explicit_path) or {}


def save_raw_config(data: Dict[str, Any], explicit_path: Optional[Path] = None) -> None:
    """Write raw JSON config to disk (pretty-printed, newline-terminated)."""
    path = explicit_path or get_user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def overlay_known_keys(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay src values into dst, but only for keys that already exist in dst."""
    for k, dst_v in list(dst.items()):
        if k not in src:
            continue
        src_v = src[k]

        if isinstance(dst_v, dict) and isinstance(src_v, dict):
            dst[k] = overlay_known_keys(dst_v, src_v)
            continue

        if dst_v is None or src_v is None or isinstance(src_v, type(dst_v)):
            dst[k] = src_v

    return dst


def merge_user_config_with_template(
    *,
    user_cfg: Dict[str, Any],
    template_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge/upgrade a user config against a template schema."""
    merged = json.loads(json.dumps(template_cfg))  # deep copy
    merged = overlay_known_keys(merged, user_cfg or {})
    if "config_version" in template_cfg:
        merged["config_version"] = template_cfg.get("config_version")
    return merged



@dataclasses.dataclass
class CallConfig:
    """
    Per-LLM-call configuration.
    """
    prompt_file: Optional[str] = None
    max_memories: Optional[int] = None
    max_messages: Optional[int] = None

    # Optional per-sector memory retrieval limits (sector -> k).
    memory_limits_by_sector: Optional[Dict[str, int]] = None


    use_memories: bool = True
    use_history: bool = True
    use_documents: bool = True
    flags: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class OpenMemoryConfig:
    """
    OpenMemory runtime configuration.

    Notes:
    - db_path is kept as the raw config string; use db_path_resolved() for the
      deterministic resolved path.
    """
    db_path: str = "./data/memory.sqlite"
    tier: Optional[str] = None
    ollama_model: Optional[str] = None
    backend_url: Optional[str] = None

    def db_path_resolved(self) -> Path:
        return resolve_app_path(self.db_path, kind="data")


@dataclasses.dataclass
class ThalamusConfig:
    project_name: str = "llm-thalamus"
    default_user_id: str = "default"

    # LLM / Ollama
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"

    # Embeddings provider/model (used by OpenMemory adapters and validation)
    embeddings_provider: str = "ollama"
    embeddings_model: Optional[str] = None

    # OpenMemory
    openmemory: OpenMemoryConfig = dataclasses.field(default_factory=OpenMemoryConfig)

    # Memory behaviour
    max_memory_results: int = 20
    enable_reflection: bool = True

    # Short-term conversation context (in-RAM rolling window)
    short_term_max_messages: int = 0  # 0 = disabled

    # On-disk JSONL chat history (message_history.py)
    message_history_max: int = 100  # 0 = disabled
    message_file: str = "chat_history.jsonl"

    # Agent / tools behaviour (reserved for future UI-directed tools)
    tools: Dict[str, dict] = dataclasses.field(default_factory=dict)
    max_tool_steps: int = 16

    # Per-call configuration (answer, reflection, etc.)
    calls: Dict[str, CallConfig] = dataclasses.field(default_factory=dict)

    # Logging
    log_level: str = "INFO"
    log_file: Path = BASE_DIR / "logs" / "thalamus.log"

    def openmemory_db_path(self) -> Path:
        """Deterministic resolved path to the OpenMemory database file."""
        return self.openmemory.db_path_resolved()

    def openmemory_db_url(self) -> str:
        """Deterministic sqlite URL for OpenMemory (openmemory-py 1.3.x expects OM_DB_URL)."""
        # openmemory-py interprets sqlite URLs of the form:
        #   sqlite:////absolute/path/to/db.sqlite
        db_path = self.openmemory_db_path()
        return f"sqlite:////{str(db_path).lstrip('/')}"

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "ThalamusConfig":
        """
        Load configuration from config/config.json (or an explicit override path).

        Uses paths.get_user_config_path() so dev vs installed behaviour is
        consistent with the rest of the project.
        """
        path = explicit_path or get_user_config_path()
        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        th_cfg = data.get("thalamus", {})
        emb_cfg = data.get("embeddings", {})
        logging_cfg = data.get("logging", {})
        tools_cfg = data.get("tools", {})
        om_cfg = data.get("openmemory", {}) or {}

        short_term_cfg = th_cfg.get("short_term_memory", {})
        short_term_max_messages = int(short_term_cfg.get("max_messages", 0))

        # Log file: use config value if present; otherwise XDG-style via paths.py
        log_file_raw = logging_cfg.get("file")
        if log_file_raw:
            log_file = Path(log_file_raw)
        else:
            log_file = get_log_dir() / "thalamus.log"

        # ----- Per-call configuration -----
        prompts_cfg = data.get("prompts", {})
        calls_cfg_raw = th_cfg.get("calls") or {}
        if not isinstance(calls_cfg_raw, dict):
            calls_cfg_raw = {}

        base_defaults: Dict[str, Any] = {
            "prompt_file": None,
            "max_memories": None,
            "max_messages": None,
            "memory_limits_by_sector": None,
            "use_memories": True,
            "use_history": True,
            "use_documents": True,
            "flags": {},
        }

        def build_call(name: str, extra: Optional[Dict[str, Any]] = None) -> CallConfig:
            defaults = dict(base_defaults)
            if extra:
                defaults.update(extra)
            raw = calls_cfg_raw.get(name, {})
            if not isinstance(raw, dict):
                raw = {}
            merged = {**defaults, **raw}

            # Coerce memory_limits_by_sector -> Optional[Dict[str, int]]
            mls = merged.get("memory_limits_by_sector", None)
            if isinstance(mls, dict):
                coerced_s: Dict[str, int] = {}
                for k, v in mls.items():
                    try:
                        coerced_s[str(k)] = int(v)
                    except Exception:
                        continue
                mls_parsed: Optional[Dict[str, int]] = coerced_s
            else:
                mls_parsed = None

            return CallConfig(
                prompt_file=merged.get("prompt_file"),
                max_memories=merged.get("max_memories"),
                max_messages=merged.get("max_messages"),
                memory_limits_by_sector=mls_parsed,
                use_memories=bool(merged.get("use_memories", True)),
                use_history=bool(merged.get("use_history", True)),
                use_documents=bool(merged.get("use_documents", True)),
                flags=dict(merged.get("flags") or {}),
            )

        calls: Dict[str, CallConfig] = {}

        # Base calls
        calls["answer"] = build_call(
            "answer",
            extra={
                "prompt_file": prompts_cfg.get(
                    "answer",
                    th_cfg.get("answer_prompt_file"),
                )
            },
        )
        calls["reflection"] = build_call(
            "reflection",
            extra={
                "prompt_file": prompts_cfg.get(
                    "reflection",
                    th_cfg.get("reflection_prompt_file"),
                )
            },
        )

        # Memory retrieval query refinement call
        calls["memory_query"] = build_call("memory_query")

        # Space / understanding calls
        calls["space_answer"] = build_call("space_answer")
        calls["space_reflection"] = build_call("space_reflection")
        calls["understand"] = build_call("understand")

        # Agent / tools section
        tools: Dict[str, dict] = {}
        if isinstance(tools_cfg, dict):
            tools = tools_cfg

        # OpenMemory section (raw path preserved; resolved via methods)
        om_path = om_cfg.get("path")
        if not isinstance(om_path, str) or not om_path.strip():
            om_path = "./data/memory.sqlite"

        openmemory = OpenMemoryConfig(
            db_path=str(om_path).strip(),
            tier=om_cfg.get("tier"),
            ollama_model=om_cfg.get("ollama_model"),
            backend_url=(om_cfg.get("backend_url").rstrip("/") if isinstance(om_cfg.get("backend_url"), str) and om_cfg.get("backend_url").strip() else None),
        )

        return cls(
            project_name=th_cfg.get("project_name", "llm-thalamus"),
            default_user_id=th_cfg.get("default_user_id", "default"),
            ollama_url=emb_cfg.get("ollama_url", "http://localhost:11434"),
            llm_model=th_cfg.get("llm_model", "qwen2.5:7b"),
            embeddings_provider=emb_cfg.get("provider", "ollama"),
            embeddings_model=emb_cfg.get("model"),
            openmemory=openmemory,
            max_memory_results=int(th_cfg.get("max_memory_results", 20)),
            enable_reflection=bool(th_cfg.get("enable_reflection", True)),
            short_term_max_messages=short_term_max_messages,
            message_history_max=int(th_cfg.get("message_history", 100) or 0),
            message_file=str(th_cfg.get("message_file", "chat_history.jsonl")),
            tools=tools,
            max_tool_steps=int(th_cfg.get("max_tool_steps", 16)),
            calls=calls,
            log_level=logging_cfg.get("level", "INFO"),
            log_file=log_file,
        )
