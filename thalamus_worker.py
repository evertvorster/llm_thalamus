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
from typing import Optional, Tuple, Any


class ThalamusWorker:
    """
    Background worker that owns a Thalamus instance.

    Public API expected by the UI:
      - ready: bool
      - event_queue: queue.Queue[tuple]
      - start()
      - stop()
      - submit_user_message(text: str)
    """

    def __init__(self) -> None:
        # Queue for UI-bound events (chat, status, control, etc.)
        self.event_queue: "queue.Queue[tuple]" = queue.Queue()
        # Queue for user messages from the UI → Thalamus
        self.request_queue: "queue.Queue[Optional[str]]" = queue.Queue()

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

    def submit_user_message(self, text: str) -> None:
        """Enqueue a user message for processing by Thalamus."""
        if not text:
            return
        if not self._ready or self._stop_event.is_set():
            return
        self.request_queue.put(text)

    # ------------------------------------------------------------------ worker thread

    def _run(self) -> None:
        """
        Worker thread entry point.

        - Import llm_thalamus and construct Thalamus.
        - Wire Thalamus.events to our queue-producing methods.
        - Emit initial chat history from OpenMemory.
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

        # 🔹 Emit initial chat history from OpenMemory for the UI warm-up
        try:
            # You can tweak k here or make it configurable later
            th.emit_initial_chat_history(k=10)
        except Exception as e:
            # Non-fatal; just log to the thalamus pane
            self.event_queue.put(("internal_error", f"Initial chat history failed: {e}"))

        # Main request loop
        while not self._stop_event.is_set():
            try:
                item = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Sentinel for shutdown
            if item is None:
                break

            # Optionally: mark LLM busy
            self.event_queue.put(("status", "llm", "busy", None))

            try:
                th.process_user_message(item)
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
