#!/usr/bin/env python3
"""
llm_thalamus – single-threaded controller / message router.

Responsibilities:
- Load configuration and external LLM prompt templates from config/.
- Connect to a local Ollama LLM instance.
- Coordinate with the memory module (OpenMemory) for retrieval + reflection.
- Expose a simple event interface for the UI:
    - chat messages
    - status updates
    - thalamus-control (debug) entries
    - session lifecycle events

Heavy lifting stays in modules (OpenMemory, Ollama, future tools). Thalamus just
passes messages and glues things together, single-threaded.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

from memory_retrieval import query_memories
from memory_storage import store_semantic


# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"


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

    # Prompt templates (plain text files under config/)
    prompt_answer: Path = BASE_DIR / "config" / "prompt_answer.txt"
    prompt_reflection: Path = BASE_DIR / "config" / "prompt_reflection.txt"
    # Reserved for future retrieval-plan call (not used yet)
    prompt_retrieval_plan: Path = BASE_DIR / "config" / "prompt_retrieval_plan.txt"

    # Logging
    log_level: str = "INFO"
    log_file: Path = BASE_DIR / "logs" / "thalamus.log"

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "ThalamusConfig":
        path = explicit_path or CONFIG_PATH
        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        th_cfg = data.get("thalamus", {})
        emb_cfg = data.get("embeddings", {})
        logging_cfg = data.get("logging", {})
        prompts_cfg = data.get("prompts", {})

        def resolve_prompt(key: str, default_rel: str) -> Path:
            p = prompts_cfg.get(key, default_rel)
            p_path = Path(p)
            if not p_path.is_absolute():
                p_path = BASE_DIR / p_path
            return p_path

        ollama_url = emb_cfg.get("ollama_url", "http://localhost:11434")

        return cls(
            project_name=th_cfg.get("project_name", "llm-thalamus"),
            default_user_id=th_cfg.get("default_user_id", "default"),
            ollama_url=ollama_url,
            llm_model=th_cfg.get(
                "llm_model",
                os.environ.get("THALAMUS_LLM_MODEL", "qwen2.5:7b"),
            ),
            max_memory_results=int(th_cfg.get("max_memory_results", 20)),
            enable_reflection=bool(th_cfg.get("enable_reflection", True)),
            prompt_answer=resolve_prompt("answer", "config/prompt_answer.txt"),
            prompt_reflection=resolve_prompt("reflection", "config/prompt_reflection.txt"),
            prompt_retrieval_plan=resolve_prompt(
                "retrieval_plan", "config/prompt_retrieval_plan.txt"
            ),
            log_level=logging_cfg.get("level", "INFO"),
            log_file=Path(logging_cfg.get("file", "./logs/thalamus.log")),
        )


# ---------------------------------------------------------------------------
# Prompt manager – external plain-text templates
# ---------------------------------------------------------------------------


class PromptManager:
    def __init__(self, cfg: ThalamusConfig) -> None:
        self.cfg = cfg
        self._cache: Dict[str, str] = {}

    def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]

        path: Optional[Path] = None
        if name == "answer":
            path = self.cfg.prompt_answer
        elif name == "reflection":
            path = self.cfg.prompt_reflection
        elif name == "retrieval_plan":
            path = self.cfg.prompt_retrieval_plan

        if path is not None and path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                self._cache[name] = text
                return text
            except Exception:
                pass

        if name == "answer":
            text = (
                "You are a helpful local assistant. Use any provided memories only "
                "when they are clearly relevant, otherwise ignore them. Answer in "
                "a clear, conversational tone. Do not output tool calls or JSON."
            )
        elif name == "reflection":
            text = (
                "You write long-term memory notes for this assistant. From the "
                "conversation, extract only stable facts, preferences, ongoing "
                "projects, or plans that might be useful later. Return plain text."
            )
        else:
            text = "You are a helpful assistant."

        self._cache[name] = text
        return text


# ---------------------------------------------------------------------------
# Event interface (Thalamus → UI or other frontends)
# ---------------------------------------------------------------------------


class ThalamusEvents:
    def __init__(self) -> None:
        self.on_chat_message: Optional[Callable[[str, str], None]] = None
        self.on_status_update: Optional[Callable[[str, str, Optional[str]], None]] = None
        self.on_thalamus_control_entry: Optional[Callable[[str, str], None]] = None
        self.on_session_started: Optional[Callable[[], None]] = None
        self.on_session_ended: Optional[Callable[[], None]] = None

    def emit_chat(self, role: str, content: str) -> None:
        if self.on_chat_message:
            self.on_chat_message(role, content)

    def emit_status(self, subsystem: str, status: str, detail: Optional[str] = None) -> None:
        if self.on_status_update:
            self.on_status_update(subsystem, status, detail)

    def emit_control_entry(self, label: str, raw_text: str) -> None:
        if self.on_thalamus_control_entry:
            self.on_thalamus_control_entry(label, raw_text)

    def emit_session_started(self) -> None:
        if self.on_session_started:
            self.on_session_started()

    def emit_session_ended(self) -> None:
        if self.on_session_ended:
            self.on_session_ended()


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: List[Dict[str, str]], timeout: int = 600) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content", "")
        if not isinstance(content, str):
            content = str(content)
        return content


# ---------------------------------------------------------------------------
# Memory wrapper
# ---------------------------------------------------------------------------


class MemoryModule:
    def __init__(self, user_id: str, max_k: int) -> None:
        self.user_id = user_id
        self.max_k = max_k

    def retrieve_relevant_memories(self, query: str) -> str:
        try:
            return query_memories(
                query=query,
                user_id=self.user_id,
                k=self.max_k,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Memory retrieval failed: %s", e, exc_info=True
            )
            return ""

    def store_reflection(self, reflection_text: str) -> None:
        text = reflection_text.strip()
        if not text:
            return
        try:
            store_semantic(
                content=text,
                tags=["reflection", "session_summary"],
                metadata={"kind": "semantic", "source": "thalamus_reflection"},
                user_id=self.user_id,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Storing reflection failed: %s", e, exc_info=True
            )


# ---------------------------------------------------------------------------
# Thalamus core
# ---------------------------------------------------------------------------


class Thalamus:
    def __init__(self, config: Optional[ThalamusConfig] = None) -> None:
        self.config = config or ThalamusConfig.load()
        self.events = ThalamusEvents()
        self.logger = logging.getLogger("thalamus")
        self._setup_logging()

        self.prompts = PromptManager(self.config)
        self.ollama = OllamaClient(
            base_url=self.config.ollama_url,
            model=self.config.llm_model,
        )
        self.memory = MemoryModule(
            user_id=self.config.default_user_id,
            max_k=self.config.max_memory_results,
        )

        self.last_user_message: Optional[str] = None
        self.last_assistant_message: Optional[str] = None

        self.logger.info(
            "Thalamus initialised – project=%s, user_id=%s, model=%s",
            self.config.project_name,
            self.config.default_user_id,
            self.config.llm_model,
        )

        self.events.emit_status("thalamus", "connected", "idle")
        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("memory", "connected", "idle")

    # ------------------------------------------------------------------ main API

    def process_user_message(self, user_message: str) -> str:
        text = user_message.strip()
        if not text:
            return ""

        session_id = self._new_session_id()

        # NEW: explicit marker for LLM session start
        self._debug_log(
            session_id,
            "llm_session",
            "New LLM session starting: will run answer (+ reflection if enabled).",
        )

        self.events.emit_session_started()
        self.events.emit_status("thalamus", "busy", f"session {session_id}")
        self.events.emit_status("llm", "busy", "answering")
        self.events.emit_status("memory", "busy", "retrieving")

        self.events.emit_chat("user", text)
        self._debug_log(session_id, "pipeline", f"User message received:\n{text}")

        memories_block = self.memory.retrieve_relevant_memories(text)
        if memories_block:
            self._debug_log(
                session_id,
                "memory",
                f"Retrieved memories block:\n{memories_block}",
            )
        else:
            self._debug_log(session_id, "memory", "No memories retrieved.")

        self.events.emit_status("memory", "connected", "idle")

        try:
            answer = self._call_llm_answer(
                session_id=session_id,
                user_message=text,
                previous_user_message=self.last_user_message,
                memories_block=memories_block,
            )
        except Exception as e:
            self.logger.exception("LLM answer call failed")
            self.events.emit_status("llm", "error", str(e))
            self.events.emit_status("thalamus", "error", "LLM call failed")
            self.events.emit_session_ended()
            raise

        self.last_user_message = text
        self.last_assistant_message = answer

        self.events.emit_chat("assistant", answer)
        self._debug_log(session_id, "llm_answer", f"Assistant answer:\n{answer}")

        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("thalamus", "connected", "idle")

        if self.config.enable_reflection:
            try:
                self.events.emit_status("thalamus", "busy", "reflecting")
                self.events.emit_status("llm", "busy", "reflecting")

                reflection = self._call_llm_reflection(
                    session_id=session_id,
                    user_message=text,
                    assistant_message=answer,
                )
                self._debug_log(
                    session_id,
                    "reflection",
                    f"Reflection output:\n{reflection}",
                )
                self.memory.store_reflection(reflection)
            except Exception as e:
                self.logger.warning("Reflection step failed: %s", e, exc_info=True)
            finally:
                self.events.emit_status("llm", "connected", "idle")
                self.events.emit_status("thalamus", "connected", "idle")

        self.events.emit_session_ended()
        self.logger.info("Session %s finished", session_id)
        return answer

    # ------------------------------------------------------------------ internals

    def _setup_logging(self) -> None:
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            handlers=[
                logging.FileHandler(self.config.log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _new_session_id(self) -> str:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        rand = uuid.uuid4().hex[:8]
        return f"session-{ts}-{rand}"

    def _debug_log(self, session_id: str, label: str, text: str) -> None:
        header = f"[{session_id}] {label}"
        body = f"{header}\n{text}"
        self.logger.debug(body)
        self.events.emit_control_entry(label, body)

    def _call_llm_answer(
        self,
        session_id: str,
        user_message: str,
        previous_user_message: Optional[str],
        memories_block: str,
    ) -> str:
        system_prompt = self.prompts.get("answer")

        parts: List[str] = []
        if memories_block:
            parts.append("Relevant memories:\n" + memories_block)
        else:
            parts.append("Relevant memories:\n(none found)")

        if previous_user_message:
            parts.append("Previous user message:\n" + previous_user_message)

        parts.append("Current user message:\n" + user_message)
        user_prompt = "\n\n".join(parts)

        self._debug_log(
            session_id,
            "prompt_answer",
            f"System prompt (from file):\n{system_prompt}\n\nUser payload:\n{user_prompt}",
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.ollama.chat(messages)

    def _call_llm_reflection(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> str:
        system_prompt = self.prompts.get("reflection")

        user_prompt = (
            "User message:\n"
            f"{user_message}\n\n"
            "Assistant reply:\n"
            f"{assistant_message}\n\n"
            "Write memory notes that will be useful in future turns."
        )

        self._debug_log(
            session_id,
            "prompt_reflection",
            f"System prompt (from file):\n{system_prompt}\n\nUser payload:\n{user_prompt}",
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.ollama.chat(messages)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    _ = argv
    th = Thalamus()
    print("llm_thalamus CLI – type messages, Ctrl+C to exit.\n")

    try:
        while True:
            try:
                user_msg = input("you> ")
            except EOFError:
                break
            if not user_msg.strip():
                continue
            answer = th.process_user_message(user_msg)
            print(f"ai> {answer}\n")
    except KeyboardInterrupt:
        print("\nExiting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
