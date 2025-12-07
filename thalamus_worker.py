# thalamus_worker.py (new module)

import threading
import queue
import importlib

class ThalamusWorker:
    def __init__(self):
        self.request_queue: queue.Queue[str] = queue.Queue()
        self.event_queue:   queue.Queue[tuple] = queue.Queue()
        self._stop_event = threading.Event()
        self._ready = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    # --- public API ---

    @property
    def ready(self) -> bool:
        return self._ready

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.request_queue.put(None)   # sentinel
        # optional: join with timeout

    def submit_user_message(self, text: str):
        """Called from UI thread when user hits Send."""
        if self._ready and not self._stop_event.is_set():
            self.request_queue.put(text)

    # --- internal thread loop ---

    def _run(self):
        # 1. Import and construct Thalamus inside the worker thread
        try:
            module = importlib.import_module("llm_thalamus")
            ThalamusClass = getattr(module, "Thalamus")
            self.thalamus = ThalamusClass()
        except Exception as e:
            self.event_queue.put(("internal_error", str(e)))
            return

        # 2. Wire Thalamus events to queue-producer methods
        ev = self.thalamus.events
        ev.on_chat_message = self._on_chat_message
        ev.on_status_update = self._on_status_update
        ev.on_thalamus_control_entry = self._on_control_entry
        ev.on_session_started = self._on_session_started
        ev.on_session_ended = self._on_session_ended

        # 3. Tell UI that Thalamus is ready
        self._ready = True
        self.event_queue.put(("internal_ready",))

        # 4. Main request loop
        while not self._stop_event.is_set():
            try:
                item = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:   # sentinel
                break

            # Optionally: mark LLM busy
            self.event_queue.put(("status", "llm", "busy", None))

            try:
                self.thalamus.process_user_message(item)
            except Exception as e:
                self.event_queue.put(("internal_error", str(e)))

            # Optionally: mark LLM idle
            self.event_queue.put(("status", "llm", "idle", None))

    # --- event forwarders (called on worker thread) ---

    def _on_chat_message(self, role, content):
        self.event_queue.put(("chat", role, content))

    def _on_status_update(self, subsystem, status, detail):
        self.event_queue.put(("status", subsystem, status, detail))

    def _on_control_entry(self, label, text):
        self.event_queue.put(("control", label, text))

    def _on_session_started(self):
        self.event_queue.put(("session_started",))

    def _on_session_ended(self):
        self.event_queue.put(("session_ended",))
