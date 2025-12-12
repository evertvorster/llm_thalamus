#!/usr/bin/env python3
"""
llm_thalamus_internal.config

Configuration dataclasses and loader for llm-thalamus.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, Optional

from paths import get_user_config_path, get_log_dir

# Project root (same directory as llm_thalamus.py)
BASE_DIR = Path(__file__).resolve().parent.parent


@dataclasses.dataclass
class CallConfig:
    """
    Per-LLM-call configuration.

    For now this is a thin container for limits and feature flags.
    In a later pass we'll also use `prompt_file` to load the actual
    template text from disk.
    """
    prompt_file: Optional[str] = None
    max_memories: Optional[int] = None
    max_messages: Optional[int] = None
    use_memories: bool = True
    use_history: bool = True
    use_documents: bool = True
    flags: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ThalamusConfig:
    project_name: str = "llm-thalamus"
    default_user_id: str = "default"

    # LLM / Ollama
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"

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
            return CallConfig(
                prompt_file=merged.get("prompt_file"),
                max_memories=merged.get("max_memories"),
                max_messages=merged.get("max_messages"),
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

        return cls(
            project_name=th_cfg.get("project_name", "llm-thalamus"),
            default_user_id=th_cfg.get("default_user_id", "default"),
            ollama_url=emb_cfg.get("ollama_url", "http://localhost:11434"),
            llm_model=th_cfg.get("llm_model", "qwen2.5:7b"),
            max_memory_results=int(th_cfg.get("max_memory_results", 20)),
            enable_reflection=bool(th_cfg.get("enable_reflection", True)),
            short_term_max_messages=short_term_max_messages,
            tools=tools,
            max_tool_steps=int(th_cfg.get("max_tool_steps", 16)),
            calls=calls,
            log_level=logging_cfg.get("level", "INFO"),
            log_file=log_file,
        )
