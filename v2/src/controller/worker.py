from __future__ import annotations

import threading
import json
import requests

from PySide6.QtCore import QObject, Signal, Slot, QThread

from chat_history import append_turn, read_tail


class ControllerWorker(QObject):
    busy_changed = Signal(bool)
    assistant_message = Signal(str)
    error = Signal(str)

    # --- thinking channel (ephemeral, per-request) ---
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()

    # role, content, ts
    history_turn = Signal(str, str, str)

    # single log line intended ...
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

    def shutdown(self) -> None:
        """
        Stop the worker QThread cleanly so we don't get:
          'QThread: Destroyed while thread is still running'
        """
        try:
            if self._thread.isRunning():
                self.log_line.emit("[ui] shutdown: stopping controller thread")
                self._thread.quit()
                self._thread.wait(2000)
        except Exception as e:
            # Don't raise during shutdown
            try:
                self.log_line.emit(f"[ui] shutdown: exception: {e}")
            except Exception:
                pass

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
            "stream": True,
        }

        # Buffer the final assistant response (non-streaming UX) while streaming
        # thinking deltas live.
        response_parts: list[str] = []
        thinking_started_emitted = False

        def _emit_thinking_started_once() -> None:
            nonlocal thinking_started_emitted
            if not thinking_started_emitted:
                thinking_started_emitted = True
                self.thinking_started.emit()

        try:
            # timeout=(connect, read)
            r = requests.post(url, json=payload, timeout=(10, 300), stream=True)
            r.raise_for_status()

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except Exception as e:
                    raise RuntimeError(f"Malformed Ollama stream line: {line!r}") from e

                # Some servers may include an explicit error field.
                if data.get("error"):
                    raise RuntimeError(str(data.get("error")))

                # Thinking (optional, model-dependent)
                thinking_tok = data.get("thinking")
                if thinking_tok:
                    _emit_thinking_started_once()
                    self.thinking_delta.emit(str(thinking_tok))

                # Response token (always buffer)
                resp_tok = data.get("response")
                if resp_tok:
                    response_parts.append(str(resp_tok))

                if data.get("done") is True:
                    break

        finally:
            # Guarantee lifecycle closure if we ever emitted thinking_started.
            if thinking_started_emitted:
                self.thinking_finished.emit()

        return "".join(response_parts).strip()

