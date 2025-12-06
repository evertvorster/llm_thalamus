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

from tool_registry import ToolRegistry
from memory_retrieval import query_memories
from memory_storage import store_semantic

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


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

    # Agent / tools behaviour
    tools: Dict[str, dict] = dataclasses.field(default_factory=dict)
    max_tool_steps: int = 16

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
        tools_cfg = data.get("tools", {})

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
            tools=tools_cfg,
            max_tool_steps=int(th_cfg.get("max_tool_steps", 16)),
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
            except Exception:
                text = ""
        else:
            text = ""

        self._cache[name] = text
        return text


# ---------------------------------------------------------------------------
# Simple event bus
# ---------------------------------------------------------------------------


class ThalamusEvents:
    def __init__(self) -> None:
        # MUST use these names so the UI can hook into them
        self.on_chat_message: Optional[Callable[[str, str], None]] = None
        self.on_status_update: Optional[Callable[[str, str, Optional[str]], None]] = None
        self.on_thalamus_control_entry: Optional[Callable[[str, str], None]] = None
        self.on_session_started: Optional[Callable[[], None]] = None
        self.on_session_ended: Optional[Callable[[], None]] = None

    def emit_chat(self, role: str, text: str) -> None:
        if self.on_chat_message:
            self.on_chat_message(role, text)

    def emit_status(self, component: str, state: str, detail: Optional[str] = None) -> None:
        if self.on_status_update:
            self.on_status_update(component, state, detail)

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
                user_id=self.user_id,
            )
        except Exception as e:
            logging.getLogger("thalamus").warning(
                "Memory storage failed: %s", e, exc_info=True
            )


# ---------------------------------------------------------------------------
# Thalamus – main controller
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

        # Tool registry for LLM-accessible tools (memory, etc.)
        self.tools = ToolRegistry(
            tools_config=self.config.tools,
            memory_module=self.memory,
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

    # ------------------------------------------------------------------ public API

    def process_user_message(self, user_message: str) -> str:
        text = user_message.strip()
        if not text:
            return ""

        session_id = self._new_session_id()
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

    def _parse_llm_control_message(self, raw: str) -> Optional[Dict[str, object]]:
        """Try to parse a JSON control message from the LLM.

        Returns a dict with at least a "type" key on success, or None
        if the content is not valid control JSON (treated as plain text).
        """
        text = raw.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        if "type" not in data:
            return None
        return data

    def _call_llm_answer(
        self,
        session_id: str,
        user_message: str,
        previous_user_message: Optional[str],
        memories_block: str,
    ) -> str:
        """Call the LLM for an answer, allowing it to use tools before replying.

        The LLM can emit JSON control messages of the form:
        - {"type": "tool_discovery", "tool": "all" | "name"}
        - {"type": "tool_call", "tool": "name", "args": {...}}
        - {"type": "final_answer", "message": "..."}

        Anything that is not valid control JSON is treated as the final
        user-visible answer.
        """
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

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        self._debug_log(
            session_id,
            "llm_session",
            "New LLM session starting (tools enabled).",
        )

        max_steps = max(1, int(self.config.max_tool_steps))

        last_content: str = ""

        for step in range(max_steps):
            content = self.ollama.chat(messages)
            if not isinstance(content, str):
                content = str(content)
            last_content = content
            control = self._parse_llm_control_message(content)

            if control is None:
                # Plain text – treat as final answer.
                self._debug_log(
                    session_id,
                    "llm_answer_raw",
                    f"Final answer (no control JSON) at step {step}:\n{content}",
                )
                return content

            mtype = str(control.get("type", "")).strip()
            self._debug_log(
                session_id,
                "llm_control",
                f"Control message at step {step}: {control}",
            )

            if mtype == "final_answer":
                answer_text = str(control.get("message", "")).strip()
                if answer_text:
                    return answer_text
                # Fallback: if message missing/empty, return raw content.
                return content

            if mtype == "tool_discovery":
                tool_key = str(control.get("tool", "all"))
                result = self.tools.discover(tool_key)
                self._debug_log(
                    session_id,
                    "tool_discovery",
                    f"Tool discovery for {tool_key!r} -> {result}",
                )
                # Feed back to the model as a tool message.
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "tool",
                        "name": "tool_discovery",
                        "content": result,
                    }
                )
                continue

            if mtype == "tool_call":
                tool_name = control.get("tool")
                args = control.get("args") or {}
                self._debug_log(
                    session_id,
                    "tool_call",
                    f"Tool call requested: {tool_name!r} args={args}",
                )
                result = self.tools.execute(
                    session_id, str(tool_name) if tool_name else "", args
                )
                self._debug_log(
                    session_id,
                    "tool_result",
                    f"Tool result for {tool_name!r}:\n{result}",
                )
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "tool",
                        "name": str(tool_name) if tool_name else "unknown",
                        "content": result,
                    }
                )
                continue

            # Unknown control type – fall back to treating as final answer.
            self._debug_log(
                session_id,
                "llm_control_unknown",
                f"Unknown control type {mtype!r}, returning raw content as answer.",
            )
            return content

        # Safety fallback if the model never sends a final answer.
        self._debug_log(
            session_id,
            "llm_session",
            f"Max tool steps ({max_steps}) reached; returning last content as answer.",
        )
        return last_content

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
