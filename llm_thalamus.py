#!/usr/bin/env python3
"""
llm_thalamus – simplified: no system prompt for the answer step.

The LLM receives only:
- Current time
- User message
- Top-N relevant memories (from config)
- Last-M conversation messages (from config)
- Any open documents (full text)
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
from datetime import datetime

import requests

from memory_retrieval import query_memories
from memory_storage import store_semantic

BASE_DIR = Path(__file__).resolve().parent
local_cfg = BASE_DIR / "config" / "config.json"
system_cfg = Path("/etc/thalamus/config.json")

if local_cfg.exists():
    CONFIG_PATH = local_cfg
elif system_cfg.exists():
    CONFIG_PATH = system_cfg
else:
    raise FileNotFoundError("Missing config.json")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ThalamusConfig:
    project_name: str = "llm-thalamus"
    default_user_id: str = "default"

    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"

    max_memory_results: int = 20
    enable_reflection: bool = True
    short_term_max_messages: int = 0

    tools: Dict[str, dict] = dataclasses.field(default_factory=dict)
    max_tool_steps: int = 16

    # Only reflection prompt remains
    prompt_reflection: Path = BASE_DIR / "config" / "prompt_reflection.txt"

    log_level: str = "INFO"
    log_file: Path = BASE_DIR / "logs" / "thalamus.log"

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "ThalamusConfig":
        path = explicit_path or CONFIG_PATH
        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        th = data.get("thalamus", {})
        emb = data.get("embeddings", {})
        logc = data.get("logging", {})
        prompts = data.get("prompts", {})

        def resolve_prompt(key: str, default_rel: str):
            p = prompts.get(key, default_rel)
            p = Path(p)
            if not p.is_absolute():
                p = BASE_DIR / p
            return p

        short_cfg = th.get("short_term_memory", {})
        return cls(
            project_name=th.get("project_name", "llm-thalamus"),
            default_user_id=th.get("default_user_id", "default"),
            ollama_url=emb.get("ollama_url", "http://localhost:11434"),
            llm_model=th.get("llm_model",
                             os.environ.get("THALAMUS_LLM_MODEL", "qwen2.5:7b")),
            max_memory_results=int(th.get("max_memory_results", 20)),
            enable_reflection=bool(th.get("enable_reflection", True)),
            short_term_max_messages=int(short_cfg.get("max_messages", 0)),
            tools=data.get("tools", {}),
            max_tool_steps=int(th.get("max_tool_steps", 16)),
            prompt_reflection=resolve_prompt("reflection", "config/prompt_reflection.txt"),
            log_level=logc.get("level", "INFO"),
            log_file=Path(logc.get("file", "./logs/thalamus.log")),
        )


# ---------------------------------------------------------------------------
# Prompt manager (only used for reflection)
# ---------------------------------------------------------------------------

class PromptManager:
    def __init__(self, cfg: ThalamusConfig) -> None:
        self.cfg = cfg
        self._cache: Dict[str, str] = {}

    def get(self, name: str) -> str:
        if name in self._cache:
            return self._cache[name]
        if name == "reflection":
            path = self.cfg.prompt_reflection
        else:
            return ""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        self._cache[name] = text
        return text


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class ThalamusEvents:
    def __init__(self):
        self.on_chat_message = None
        self.on_status_update = None
        self.on_thalamus_control_entry = None
        self.on_session_started = None
        self.on_session_ended = None

    def emit_chat(self, role, text):
        if self.on_chat_message:
            self.on_chat_message(role, text)

    def emit_status(self, c, s, d=None):
        if self.on_status_update:
            self.on_status_update(c, s, d)

    def emit_control_entry(self, label, raw):
        if self.on_thalamus_control_entry:
            self.on_thalamus_control_entry(label, raw)

    def emit_session_started(self):
        if self.on_session_started:
            self.on_session_started()

    def emit_session_ended(self):
        if self.on_session_ended:
            self.on_session_ended()


# ---------------------------------------------------------------------------
# Short-term memory
# ---------------------------------------------------------------------------

class ConversationHistory:
    def __init__(self, max_messages: int):
        self.max = max_messages
        self.buf = []

    def add(self, role, text):
        if self.max <= 0:
            return
        self.buf.append({"role": role, "text": text})
        if len(self.buf) > self.max:
            self.buf = self.buf[-self.max:]

    def formatted_block(self) -> str:
        if self.max <= 0 or not self.buf:
            return ""
        return "\n".join(f"{m['role'].capitalize()}: {m['text']}" for m in self.buf)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryModule:
    def __init__(self, user_id, max_k):
        self.user_id = user_id
        self.max_k = max_k

    def retrieve_relevant_memories(self, query: str) -> str:
        try:
            return query_memories(query=query, user_id=self.user_id, k=self.max_k)
        except Exception:
            logging.getLogger("thalamus").exception("Memory retrieval failed")
            return ""

    def store_reflection(self, text: str):
        text = text.strip()
        if not text:
            return
        try:
            store_semantic(content=text, user_id=self.user_id)
        except Exception:
            logging.getLogger("thalamus").exception("Memory store failed")


# ---------------------------------------------------------------------------
# Thalamus core
# ---------------------------------------------------------------------------

class Thalamus:
    def __init__(self, config=None):
        self.config = config or ThalamusConfig.load()
        self.events = ThalamusEvents()

        self.logger = logging.getLogger("thalamus")
        self._setup_logging()

        self.prompts = PromptManager(self.config)
        self.ollama = OllamaClient(self.config.ollama_url, self.config.llm_model)
        self.memory = MemoryModule(self.config.default_user_id,
                                   self.config.max_memory_results)

        self.open_documents = []
        self.history = ConversationHistory(self.config.short_term_max_messages)

        self.last_user_message = None
        self.last_assistant_message = None

        self.events.emit_status("thalamus", "connected", "idle")
        self.events.emit_status("llm", "connected", "idle")
        self.events.emit_status("memory", "connected", "idle")

    # Open docs -------------------------------------------------------------

    def set_open_documents(self, docs):
        self.open_documents = list(docs or [])

    # ----------------------------------------------------------------------

    def process_user_message(self, user_message: str) -> str:
        text = user_message.strip()
        if not text:
            return ""

        sid = self._new_session_id()
        self.events.emit_session_started()
        self.events.emit_chat("user", text)

        memories = self.memory.retrieve_relevant_memories(text)
        recent = self.history.formatted_block()

        answer = self._call_llm_answer(
            sid, user_message=text, memories_block=memories,
            recent_conversation_block=recent
        )

        self.history.add("user", text)
        self.history.add("assistant", answer)

        self.events.emit_chat("assistant", answer)

        if self.config.enable_reflection:
            reflection = self._call_llm_reflection(
                sid, user_message=text, assistant_message=answer
            )
            self.memory.store_reflection(reflection)

        self.events.emit_session_ended()
        return answer

    # ----------------------------------------------------------------------

    def _call_llm_answer(self, sid, user_message, memories_block, recent_conversation_block):
        """LLM receives *no system prompt*."""

        now = datetime.now().isoformat(timespec="seconds")

        parts = [
            f"User message:\n{user_message}",
            f"Current time: {now}",
        ]

        n = self.config.max_memory_results
        if memories_block:
            parts.append(f"Top {n} memories:\n{memories_block}")
        else:
            parts.append(f"Top {n} memories:\n(none)")

        m = self.config.short_term_max_messages
        if recent_conversation_block:
            parts.append(f"Last {m} messages:\n{recent_conversation_block}")

        if self.open_documents:
            lines = ["Relevant open documents:"]
            for d in self.open_documents:
                name = d.get("name") or d.get("filename") or "(unnamed)"
                text = d.get("text") or d.get("content") or ""
                lines.append(f"{name} containing:\n{text}")
            parts.append("\n".join(lines))

        payload = "\n\n".join(parts)

        self._debug(sid, "llm_answer_prompt", payload)

        msg = [{"role": "user", "content": payload}]
        return self.ollama.chat(msg)

    def _call_llm_reflection(self, sid, user_message, assistant_message):
        system_prompt = self.prompts.get("reflection")

        user_prompt = (
            f"User message:\n{user_message}\n\n"
            f"Assistant reply:\n{assistant_message}\n\n"
            "Write memory notes that will be useful later."
        )

        self._debug(sid, "llm_reflection_prompt", user_prompt)

        msg = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.ollama.chat(msg)

    # ----------------------------------------------------------------------

    def _setup_logging(self):
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        lvl = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(self.config.log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout)
            ],
        )

    def _new_session_id(self):
        return f"session-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _debug(self, sid, label, text):
        body = f"[{sid}] {label}\n{text}"
        self.logger.debug(body)
        self.events.emit_control_entry(label, body)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

class OllamaClient:
    def __init__(self, base_url, model):
        self.base = base_url.rstrip("/")
        self.model = model

    def chat(self, messages, timeout=600):
        url = f"{self.base}/api/chat"
        p = {"model": self.model, "messages": messages, "stream": False}
        r = requests.post(url, json=p, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content", "") or ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    th = Thalamus()
    print("llm_thalamus CLI. Ctrl+C to exit.\n")
    try:
        while True:
            u = input("you> ")
            if not u.strip():
                continue
            a = th.process_user_message(u)
            print("ai>", a, "\n")
    except KeyboardInterrupt:
        print("\nBye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
