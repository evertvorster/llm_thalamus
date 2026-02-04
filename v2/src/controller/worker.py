from __future__ import annotations

import json
import threading
import requests

from PySide6.QtCore import QObject, Signal, Slot, QThread

from chat_history import append_turn
from config import bootstrap_config


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    assistant_message = Signal(str)
    error = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self._cfg = cfg
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.start()

    # ---------- public API (called by UI) ----------

    @Slot(str)
    def submit_message(self, text: str) -> None:
        if not text.strip():
            return

        self.busy_changed.emit(True)

        threading.Thread(
            target=self._handle_message,
            args=(text,),
            daemon=True,
        ).start()

    @Slot()
    def reload_config(self) -> None:
        try:
            self._cfg = bootstrap_config([])
        except Exception as e:
            self.error.emit(f"Config reload failed: {e}")

    # ---------- internal logic ----------

    def _handle_message(self, text: str) -> None:
        try:
            append_turn(
                history_file=self._cfg.message_file,
                role="human",
                content=text,
                max_turns=self._cfg.message_history_max,
            )

            reply = self._call_ollama(text)

            append_turn(
                history_file=self._cfg.message_file,
                role="you",
                content=reply,
                max_turns=self._cfg.message_history_max,
            )

            self.assistant_message.emit(reply)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.busy_changed.emit(False)

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self._cfg.llm_model,
            "prompt": prompt,
            "stream": False,
        }

        r = requests.post(self._cfg.llm_url, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
