from __future__ import annotations

import threading
import requests

from PySide6.QtCore import QObject, Signal, Slot, QThread

from chat_history import append_turn, read_tail


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    assistant_message = Signal(str)
    error = Signal(str)

    # role, content, ts
    history_turn = Signal(str, str, str)

    # single log line intended for UI log window
    log_line = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self._cfg = cfg
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

        self.log_line.emit("ControllerWorker started.")

    # ---------- public API (called by UI) ----------

    @Slot(str)
    def submit_message(self, text: str) -> None:
        if not text.strip():
            return

        self.log_line.emit(f"[ui] submit_message len={len(text)}")
        self.busy_changed.emit(True)

        threading.Thread(
            target=self._handle_message,
            args=(text,),
            daemon=True,
        ).start()

    @Slot()
    def reload_config(self) -> None:
        # MVP: UI rewrites config on disk; controller reload can be improved later
        try:
            from config import bootstrap_config
            self._cfg = bootstrap_config([])
            self.log_line.emit("[cfg] reloaded config from disk")
        except Exception as e:
            self.log_line.emit(f"[cfg] reload FAILED: {e}")
            self.error.emit(f"Config reload failed: {e}")

    def emit_history(self) -> None:
        """
        Emit the last N turns from history so the UI can render them as historical.
        """
        try:
            turns = read_tail(self._cfg.message_file, limit=self._cfg.history_message_limit)
            self.log_line.emit(f"[history] loaded {len(turns)} turns from {self._cfg.message_file}")
            for t in turns:
                self.history_turn.emit(t.role, t.content, t.ts)
        except Exception as e:
            self.log_line.emit(f"[history] load FAILED: {e}")
            self.error.emit(f"History load failed: {e}")

    # ---------- internal logic ----------

    def _handle_message(self, text: str) -> None:
        try:
            append_turn(
                history_file=self._cfg.message_file,
                role="human",
                content=text,
                max_turns=self._cfg.message_history_max,
            )

            self.log_line.emit(f"[ollama] request model={self._cfg.llm_model}")
            reply = self._call_llm(text)
            self.log_line.emit(f"[ollama] response len={len(reply)}")

            append_turn(
                history_file=self._cfg.message_file,
                role="you",
                content=reply,
                max_turns=self._cfg.message_history_max,
            )

            self.assistant_message.emit(reply)

        except Exception as e:
            self.log_line.emit(f"[error] LLM call failed: {e}")
            self.error.emit(f"LLM call failed: {e}")
        finally:
            self.busy_changed.emit(False)

    def _call_llm(self, prompt: str) -> str:
        if self._cfg.llm_kind != "ollama":
            raise RuntimeError(f"Unsupported llm.kind={self._cfg.llm_kind} (MVP supports only ollama)")

        url = self._cfg.llm_url.rstrip("/") + "/api/generate"
        payload = {
            "model": self._cfg.llm_model,
            "prompt": prompt,
            "stream": False,
        }

        r = requests.post(url, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()
