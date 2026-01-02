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

    # Optional per-sector memory retrieval limits for *rules* recall (sector -> k).
    rules_memory_limits_by_sector: Optional[Dict[str, int]] = None

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
            "rules_memory_limits_by_sector": None,
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

            # Coerce rules_memory_limits_by_sector -> Optional[Dict[str, int]]
            rmls = merged.get("rules_memory_limits_by_sector", None)
            if isinstance(rmls, dict):
                coerced_r: Dict[str, int] = {}
                for k, v in rmls.items():
                    try:
                        coerced_r[str(k)] = int(v)
                    except Exception:
                        continue
                rmls_parsed: Optional[Dict[str, int]] = coerced_r
            else:
                rmls_parsed = None

            return CallConfig(
                prompt_file=merged.get("prompt_file"),
                max_memories=merged.get("max_memories"),
                max_messages=merged.get("max_messages"),
                memory_limits_by_sector=mls_parsed,
                rules_memory_limits_by_sector=rmls_parsed,
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
            tools=tools,
            max_tool_steps=int(th_cfg.get("max_tool_steps", 16)),
            calls=calls,
            log_level=logging_cfg.get("level", "INFO"),
            log_file=log_file,
        )
