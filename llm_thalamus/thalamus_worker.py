#!/usr/bin/env python3
"""
thalamus_worker – run Thalamus + LLM in a background thread for the UI.

This keeps the Qt GUI thread responsive while:
- processing user messages with Thalamus.process_user_message()
- forwarding Thalamus events back to the UI via a thread-safe queue.
"""

import threading
import queue
import importlib
from typing import Optional, Any, Tuple


class ThalamusWorker:
    """
    Background worker that owns a Thalamus instance.

    Public API expected by the UI:
      - ready: bool
      - event_queue: queue.Queue[tuple]
      - start()
      - stop()
      - submit_user_message(text: str, doc_handles: list[dict] | None = None)
    """

    def __init__(self) -> None:
        # Queue for UI-bound events (chat, status, control, etc.)
        self.event_queue: "queue.Queue[tuple]" = queue.Queue()
        # Queue for user messages from the UI → Thalamus
        # Each item is either:
        #   - None                 → sentinel to shut down
        #   - str                  → just the user text (legacy)
        #   - (str, list|None)     → (user_text, active_document_handles)
        self.request_queue: "queue.Queue[Optional[Any]]" = queue.Queue()

        self._stop_event = threading.Event()
        self._ready = False
        self._thread = threading.Thread(target=self._run, daemon=True)

        self.thalamus = None

    # ------------------------------------------------------------------ public API

    @property
    def ready(self) -> bool:
        """True once Thalamus has been constructed successfully."""
        return self._ready

    def start(self) -> None:
        """Start the worker thread."""
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        """Signal the worker to exit and unblock its queue."""
        self._stop_event.set()
        # Unblock the queue if it's waiting
        try:
            self.request_queue.put_nowait(None)
        except Exception:
            pass

    def submit_user_message(self, text: str, open_documents: Optional[list] = None) -> None:
        """Enqueue a user message (and optional open documents) for Thalamus."""
        if not text:
            return
        if not self._ready or self._stop_event.is_set():
            return

        # For backward compatibility we still accept plain strings,
        # but when docs are provided we enqueue a (text, docs) tuple.
        if open_documents is None:
            self.request_queue.put(text)
        else:
            self.request_queue.put((text, open_documents))


    # ------------------------------------------------------------------ worker thread

    def _run(self) -> None:
        """
        Worker thread entry point.

        - Import llm_thalamus and construct Thalamus.
        - Wire Thalamus.events to our queue-producing methods.
        - Process user messages in a loop.
        """
        try:
            module = importlib.import_module("llm_thalamus")
            ThalamusClass = getattr(module, "Thalamus")
            th = ThalamusClass()
        except Exception as e:
            # Tell UI something went wrong during startup
            self.event_queue.put(("internal_error", f"Failed to initialise Thalamus: {e}"))
            return

        self.thalamus = th

        # Wire Thalamus events so they go into event_queue instead of the UI directly
        ev = th.events
        ev.on_chat_message = self._on_chat_message
        ev.on_status_update = self._on_status_update
        ev.on_thalamus_control_entry = self._on_control_entry
        ev.on_session_started = self._on_session_started
        ev.on_session_ended = self._on_session_ended

        # Mark as ready and notify the UI
        self._ready = True
        self.event_queue.put(("internal_ready",))
        
        # Emit startup chat history (file-backed via Thalamus)
        try:
            th.emit_initial_chat_history(k=20)
        except Exception as e:
            self.event_queue.put(("internal_error", f"Failed to emit initial chat history: {e}"))


        # Main request loop
        while not self._stop_event.is_set():
            try:
                item = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Sentinel for shutdown
            if item is None:
                break

            # Decode queue payload: support both legacy (plain string)
            # and new (text, open_documents) tuples.
            if isinstance(item, tuple) and len(item) == 2:
                user_text, open_documents = item
            else:
                user_text = item
                open_documents = None

            # Optionally: mark LLM busy
            self.event_queue.put(("status", "llm", "busy", None))

            try:
                th.process_user_message(str(user_text), open_documents=open_documents)
            except Exception as e:
                self.event_queue.put(("internal_error", f"Error in process_user_message: {e}"))

            # Optionally: mark LLM idle
            self.event_queue.put(("status", "llm", "idle", None))


    # ------------------------------------------------------------------ Thalamus event forwarders

    def _on_chat_message(self, role: str, text: str) -> None:
        # Called on the worker thread by Thalamus
        self.event_queue.put(("chat", role, text))

    def _on_status_update(self, subsystem: str, status: str, detail: Optional[str]) -> None:
        self.event_queue.put(("status", subsystem, status, detail))

    def _on_control_entry(self, label: str, text: str) -> None:
        self.event_queue.put(("control", label, text))

    def _on_session_started(self) -> None:
        self.event_queue.put(("session_started",))

    def _on_session_ended(self) -> None:
        self.event_queue.put(("session_ended",))
