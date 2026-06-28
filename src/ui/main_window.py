"""MainWindow — the central Qt window connecting PiRPCBridge signals to the UI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer, QThread, QObject, Signal, QBuffer, QIODevice, QByteArray
from PySide6.QtMultimedia import (
    QAudioSource,
    QAudioFormat,
    QMediaDevices,
)
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,

    QLineEdit,
    QProgressDialog,
    QRadioButton,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controller.pi_bridge import PiRPCBridge
from controller.stt import (
    available_backends, get_backend, SttBackend,
    BackendUnavailable, model_size_human,
)
from ui.chat_renderer import ChatRenderer
from ui.command_palette import CommandPalette
from ui.attachment_bar import AttachmentBar
from ui.model_dialog import ModelPickerDialog
from ui.session_dialog import SessionDialog
from ui.widgets import BrainWidget

from PySide6.QtCore import QDateTime


# ── Worker for background model downloads ───────────────────────


class _DownloadWorker(QObject):
    """Downloads an STT model in a background thread.

    Usage::

        thread = QThread()
        worker = _DownloadWorker(backend, model_name)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda m: ...)
        worker.error.connect(lambda e: ...)
        thread.start()
    """

    finished = Signal(str)   # model name on success
    error = Signal(str)      # error message on failure

    def __init__(self, backend: SttBackend, model: str) -> None:
        super().__init__()
        self._backend = backend
        self._model = model

    def run(self) -> None:
        try:
            self._backend.download_model(self._model)
            self.finished.emit(self._model)
        except Exception as exc:
            self.error.emit(str(exc))


# ── STT language codes (Whisper-supported subset) ─────────────────

_STT_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "Auto-detect"),
    ("af", "Afrikaans"),
    ("ar", "Arabic"),
    ("de", "German"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("sw", "Swahili"),
    ("tl", "Tagalog"),
    ("xh", "Xhosa"),
    ("zh", "Chinese"),
    ("zu", "Zulu"),
]

# ── Model capability descriptions ─────────────────────────────────

_STT_MODEL_INFO: dict[str, tuple[str, str]] = {
    "tiny":         ("~150 MB", "English only, low accuracy"),
    "tiny.en":      ("~150 MB", "English only"),
    "base":         ("~300 MB", "Good English, poor multi-language"),
    "base.en":      ("~300 MB", "English only, faster"),
    "small":        ("~1.5 GB", "Good multi-language"),
    "small.en":     ("~1.5 GB", "English only, good accuracy"),
    "medium":       ("~3 GB", "Very good multi-language"),
    "medium.en":    ("~3 GB", "English only, high accuracy"),
    "large":        ("~6 GB", "Best multi-language"),
    "large-v1":     ("~6 GB", "Best multi-language"),
    "large-v2":     ("~6 GB", "Best multi-language"),
    "large-v3":     ("~6 GB", "Best multi-language (recommended)"),
    "large-v3-turbo": ("~3 GB", "Best multi-language, faster"),
    "turbo":        ("~3 GB", "Best multi-language, faster"),
    "distil-large-v2":  ("~3 GB", "Good multi-language, fast"),
    "distil-large-v3":  ("~3 GB", "Good multi-language, fast"),
    "distil-large-v3.5":("~3 GB", "Good multi-language, fast"),
}


class MainWindow(QWidget):
    """A minimal Qt window connecting PiRPCBridge signals to ChatRenderer."""

    def __init__(self, bridge: PiRPCBridge, graphics_dir: Path):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._settings = QSettings("llm-thalamus", "llm-thalamus")
        geom = self._settings.value("window/geometry")
        if geom is not None:
            self.restoreGeometry(geom)

        self._bridge = bridge
        self._streaming: bool = False
        self._busy: bool = False
        self._provider: str = ""
        self._thinking_level: str = ""
        self._modalities: list[str] = []

        # --- STT backend (lazy) ---
        self._stt_backend: SttBackend | None = None
        self._init_stt()

        # ── Recording state ────────────────────────────────────
        self._recording: bool = False
        self._recording_mode: str = "stt"  # "stt" or "raw"
        self._audio_source: QAudioSource | None = None
        self._audio_buf: QBuffer | None = None
        self._audio_format: QAudioFormat | None = None
        self._recording_file: str = ""

        # Ensure attachments directory exists
        self._attach_dir = Path.home() / ".pi" / "agent" / "sessions" / "attachments"
        self._attach_dir.mkdir(parents=True, exist_ok=True)

        # --- chat (full width) ---
        self.chat = ChatRenderer()

        self.chat_input = AttachmentBar()
        self.chat_input.sendRequested.connect(self._on_send)
        self.chat_input.textChanged.connect(self._on_input_text_changed)

        # ── slash command palette ─────────────────────────────────
        self._command_palette = CommandPalette()
        self._command_palette.attach(bridge, self.chat_input)
        self._command_palette.command_requested.connect(self._on_command_requested)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send)

        self.follow_up_button = QPushButton("Follow up")
        self.follow_up_button.setEnabled(False)
        self.follow_up_button.clicked.connect(self._on_follow_up)

        self.session_button = QPushButton("Session")
        self.session_button.clicked.connect(self._on_open_session_dialog)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)

        # --- brain (positioned between input and buttons) ---
        self.brain = BrainWidget(graphics_dir)
        self.brain.set_state("thalamus")
        self.brain.setMinimumSize(220, 220)

        self._voice_button = QPushButton("🎤 Voice")
        self._voice_button.setStyleSheet("* { padding: 4px 8px; font-size: 11pt; }")
        self._voice_button.pressed.connect(self._on_voice_pressed)
        self._voice_button.released.connect(self._on_voice_released)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.brain, 0, Qt.AlignCenter)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(4)
        buttons_col.addWidget(self._voice_button)
        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.follow_up_button)
        buttons_col.addWidget(self.session_button)

        self.configure_button = QPushButton("Settings")
        self.configure_button.clicked.connect(lambda: self._on_settings_dialog(0))
        buttons_col.addWidget(self.configure_button)

        buttons_col.addWidget(self.quit_button)
        input_row.addLayout(buttons_col)

        # --- status bar ---
        self._status_entries: dict[str, str] = {}

        self._status_frame = QFrame()
        self._status_frame.setObjectName("statusFrame")
        self._status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._status_frame.setStyleSheet(
            "#statusFrame {"
            "  border-top: 1px solid #ccc; padding: 2px 6px; background: #f5f5f7;"
            "  font-size: 9pt;"
            "}"
            "#statusFrame QLabel { color: #444; }"
        )
        status_vlayout = QVBoxLayout(self._status_frame)
        status_vlayout.setContentsMargins(0, 0, 0, 0)
        status_vlayout.setSpacing(0)

        # ── row 1: path | tokens | context | model ─────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(6, 2, 6, 2)
        row1.setSpacing(16)

        self._path_label = QLabel("\u00a0")
        self._path_label.setToolTip("Working directory and git branch")
        row1.addWidget(self._path_label)
        row1.addStretch(1)

        self._tokens_label = QLabel("\u00a0")
        self._tokens_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._tokens_label.setToolTip("Input ↑ / Output ↓ tokens (k=thousands, M=millions) — R = cache reads")
        row1.addWidget(self._tokens_label)

        self._context_label = QLabel("\u00a0")
        self._context_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._context_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._context_label.setToolTip("Context window usage — current tokens / total window size")
        row1.addWidget(self._context_label)

        self._model_label = QLabel("-")
        self._model_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._model_label.setToolTip("Provider and model.  Click to change model, Ctrl+P to cycle.")
        self._model_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_label.mousePressEvent = lambda e: self._on_open_model_picker()
        row1.addWidget(self._model_label)

        # ── thinking level (clickable) ──────────────────────
        self._thinking_label = QLabel("-")
        self._thinking_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._thinking_label.setToolTip("Thinking level.  Click to change, Shift+Tab to cycle.")
        self._thinking_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thinking_label.mousePressEvent = lambda e: self._on_thinking_level_menu()
        row1.addWidget(self._thinking_label)

        # ── modality indicators ────────────────────────────
        self._vision_icon = QLabel("\U0001f441\ufe0f")
        self._vision_icon.setToolTip("Model supports vision (images)")
        self._vision_icon.setStyleSheet("font-size: 11pt;")
        row1.addWidget(self._vision_icon)

        self._audio_icon = QLabel("\U0001f3a4")
        self._audio_icon.setToolTip("Model supports audio (voice)")
        self._audio_icon.setStyleSheet("font-size: 11pt;")
        row1.addWidget(self._audio_icon)

        status_vlayout.addLayout(row1)

        # ── row 2: toggle buttons + extension status ──────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(6, 0, 6, 2)
        row2.setSpacing(6)

        self._show_thinking_btn = QPushButton("Thinking ON")
        self._show_thinking_btn.setCheckable(True)
        self._show_thinking_btn.setChecked(True)
        self._show_thinking_btn.setFixedHeight(20)
        self._show_thinking_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 0 8px; border-radius: 3px; }"
            "QPushButton:checked { background: #4caf50; color: white; }"
            "QPushButton:!checked { background: #ccc; }"
        )
        self._show_thinking_btn.clicked.connect(self._on_toggle_thinking)
        row2.addWidget(self._show_thinking_btn)

        self._show_tools_btn = QPushButton("Tools ON")
        self._show_tools_btn.setCheckable(True)
        self._show_tools_btn.setChecked(True)
        self._show_tools_btn.setFixedHeight(20)
        self._show_tools_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 0 8px; border-radius: 3px; }"
            "QPushButton:checked { background: #4caf50; color: white; }"
            "QPushButton:!checked { background: #ccc; }"
        )
        self._show_tools_btn.clicked.connect(self._on_toggle_tools)
        row2.addWidget(self._show_tools_btn)

        # Sync button state with renderer defaults from QSettings.
        self._show_thinking_btn.setChecked(self.chat._show_thinking)
        self._show_thinking_btn.setText("Thinking ON" if self.chat._show_thinking else "Thinking OFF")
        self._show_tools_btn.setChecked(self.chat._show_tools)
        self._show_tools_btn.setText("Tools ON" if self.chat._show_tools else "Tools OFF")

        self._status_extras_label = QLabel("")
        self._status_extras_label.setToolTip("Extension status indicators (MemPalace, Memory capture)")
        self._status_extras_label.setVisible(False)
        row2.addWidget(self._status_extras_label, 1)
        status_vlayout.addLayout(row2)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self.chat, 1)
        root.addLayout(input_row)
        root.addWidget(self._status_frame)

        # --- wire signals ---
        bridge.assistant_stream_start.connect(self._on_stream_start)
        bridge.assistant_stream_delta.connect(self._on_stream_delta)
        bridge.assistant_stream_end.connect(self._on_stream_end)
        bridge.thinking_started.connect(self._on_thinking_started)
        bridge.thinking_delta.connect(self._on_thinking_delta)
        bridge.thinking_finished.connect(self._on_thinking_finished)
        bridge.tool_execution_start.connect(self._on_tool_start)
        bridge.tool_execution_update.connect(self._on_tool_update)
        bridge.tool_execution_end.connect(self._on_tool_end)
        bridge.busy_changed.connect(self._on_busy)
        bridge.error.connect(self._on_error)
        bridge.history_turn.connect(self._on_history_turn)
        bridge.history_thinking.connect(self._on_history_thinking)
        bridge.extension_ui_dialog.connect(self._on_extension_ui_dialog)
        bridge.extension_ui_notify.connect(self._on_extension_ui_notify)
        bridge.extension_ui_status.connect(self._on_extension_ui_status)

        bridge.response_received.connect(self._on_response_received)

        # ── async model capability queries ───────────────────────
        

        # brain click opens the RPC event log (placeholder for now)
        self.brain.clicked.connect(lambda: print("[brain] clicked"))

        # Track system theme changes for "system" theme mode.
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._on_system_theme_changed
        )

        # Request initial status after startup.
        QTimer.singleShot(1200, self._refresh_status_bar)

        # Batch history renders until all startup messages arrive.
        self._history_batch_pending: bool = False

        # ── keyboard shortcuts (single source of truth) ──────────
        _shortcuts: dict[str, tuple[str, object, Qt.ShortcutContext | None]] = {
            "Escape": ("Abort / close palette", self._on_escape, None),
            "Ctrl+L": ("Open model picker", self._on_open_model_picker, None),
            "Ctrl+P": ("Cycle model forward", lambda: self._bridge.send_command({"type": "cycle_model"}), None),
            "Alt+Enter": ("Queue follow-up message", self._on_follow_up, None),
            "Shift+Tab": ("Cycle thinking level", self._on_cycle_thinking_level, Qt.ApplicationShortcut),
        }
        # Also used by /hotkeys and _on_show_hotkeys.
        self._shortcut_descriptions: dict[str, str] = {}
        for keyseq, (desc, handler, ctx) in _shortcuts.items():
            self._shortcut_descriptions[keyseq] = desc
            sc = QShortcut(QKeySequence(keyseq), self)
            sc.activated.connect(handler)
            if ctx is not None:
                sc.setContext(ctx)

        # Track current session path for the session list.
        self._current_session_path: str | None = None
        self._pending_rename: str | None = None
        self._available_models: list[dict] = []
        self._session_dialog: SessionDialog | None = None
        self._session_dir_path: Path | None = None

    def closeEvent(self, event) -> None:
        """Save window layout before closing."""
        self._settings.setValue("window/geometry", self.saveGeometry())
        self.chat.persist_zoom()
        self._bridge.shutdown()
        super().closeEvent(event)

    # ── STT (speech-to-text) ────────────────────────────────────

    def _init_stt(self) -> None:
        """Try to load the first available STT backend."""
        backends = available_backends()
        if backends:
            self._stt_backend = get_backend(backends[0])

    def _start_recording(self, out_path: str) -> None:
        """Begin audio capture to *out_path* WAV file."""
        if self._recording:
            return

        device = QMediaDevices().defaultAudioInput()

        afmt = QAudioFormat()
        afmt.setSampleRate(16000)
        afmt.setChannelCount(1)
        afmt.setSampleFormat(QAudioFormat.Int16)

        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)

        source = QAudioSource(device, afmt)

        self._audio_buf = buf
        self._audio_source = source
        self._audio_format = afmt
        self._recording_file = out_path
        self._recording = True

        source.start(buf)

    # ── Auto-download + transcribe ─────────────────────────────────

    def _transcribe_file(self, file_path: str) -> None:
        """Transcribe a WAV file, auto-downloading the model first if needed."""
        if self._stt_backend is None:
            return

        model = self._settings.value("stt/model", "base")
        if not isinstance(model, str):
            model = "base"

        if not self._stt_backend.is_model_downloaded(model):
            self._download_and_transcribe(file_path, model)
            return

        self._do_transcribe(file_path, model)

    def _download_and_transcribe(self, file_path: str, model: str) -> None:
        """Download *model*, then transcribe *file_path*.

        Shows a progress dialog while the download runs in a background thread.
        """
        size_hint = model_size_human(model)
        label = f"Downloading model '{model}' {size_hint}\n"
        label += "First-time download from HuggingFace Hub."

        dlg = QProgressDialog(label, None, 0, 0, self)
        dlg.setWindowTitle("STT Model Download")
        dlg.setMinimumDuration(0)  # show immediately
        dlg.show()
        QApplication.processEvents()

        thread = QThread(self)
        worker = _DownloadWorker(self._stt_backend, model)
        worker.moveToThread(thread)

        def _on_done(m: str) -> None:
            dlg.close()
            thread.quit()
            # Wait briefly for thread cleanup.
            if thread.isRunning():
                thread.wait(3000)
            self._do_transcribe(file_path, m)

        def _on_error(err: str) -> None:
            dlg.close()
            thread.quit()
            if thread.isRunning():
                thread.wait(3000)
            QMessageBox.warning(
                self, "Download Error",
                f"Failed to download STT model '{model}':\n{err}",
            )

        worker.finished.connect(_on_done)
        worker.error.connect(_on_error)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.start()

    def _do_transcribe(self, file_path: str, model: str) -> None:
        """Transcribe *file_path* using *model* and insert result into input."""
        task_raw = self._settings.value("stt/task", "Transcribe")
        task = "translate" if str(task_raw) == "Translate to English" else "transcribe"
        lang_raw = self._settings.value("stt/language", "auto")
        lang = str(lang_raw) if lang_raw and str(lang_raw) != "auto" else None

        self._voice_button.setText("\U0001f3a4 \u2026")
        self._mic_button.setToolTip("Transcribing\u2026")
        QApplication.processEvents()

        try:
            text = self._stt_backend.transcribe(
                file_path, model=model, task=task, language=lang,
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "STT Error",
                f"Transcription failed:\n{exc}",
            )
            return
        finally:
            self._voice_button.setText("\U0001f3a4 STT")
            self._voice_button.setToolTip("Hold to record, release to process")
            # Clean up the temp file.
            try:
                import os
                os.unlink(file_path)
            except OSError:
                pass

        if text:
            cursor = self.chat_input.textCursor()
            cursor.insertText(text)
            self.chat_input.setTextCursor(cursor)

    # ── STT mic button ──────────────────────────────────────────

    def _on_send(self) -> None:
        """Handle the Send/Stop button and ChatInput Enter key."""
        raw = self.chat_input.toPlainText().strip()
        text = self.chat_input.resolve_text().strip()

        if self._busy:
            if not text:
                self._bridge.send_command({"type": "abort"})
                return
            self.chat.add_steer_message(text)
            self.chat_input.clear()
            self._bridge.send_command({"type": "steer", "message": text})
            return

        if not text:
            return
        # Use resolved text (with full paths) for display so the
        # renderer can resolve [file: /full/path] references.
        self.chat.add_turn("human", text)
        self.chat_input.clear()

        # Only audio is sent via RPC.  Images use [file: /path] text +
        # the model's read tool, which works more reliably and avoids
        # session corruption from oversized base64 payloads.
        audio = self._collect_sidebar_audio()
        if audio and "audio" in self._modalities:
            self._bridge.submit_message(text, audio=audio)
        else:
            self._bridge.submit_message(text)

    def _on_follow_up(self) -> None:
        """Queue a follow-up message for after the agent finishes."""
        raw = self.chat_input.toPlainText().strip()
        text = self.chat_input.resolve_text().strip()
        if not text:
            return
        self.chat.add_steer_message(f"[follow-up] {raw}")
        self.chat_input.clear()

        cmd: dict = {"type": "follow_up", "message": text}
        audio = self._collect_sidebar_audio()
        if audio and "audio" in self._modalities:
            cmd["audio"] = audio
        self._bridge.send_command(cmd)

    def _on_voice_pressed(self) -> None:
        """Voice button pressed — start recording."""
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd_hh-mm-ss")
        mode = self._settings.value("stt/voice_mode", "stt")
        self._recording_mode = mode

        if mode == "direct":
            out_path = str(self._attach_dir / f"recording-{ts}.wav")
            tip = "Recording… release to send"
        else:
            out_path = f"/tmp/llm-thalamus-recording-{ts}.wav"
            tip = "Recording… release to transcribe"

        self._start_recording(out_path)
        self._voice_button.setText("\U0001f3a4 \u25a0")
        self._voice_button.setStyleSheet(
            "* { padding: 4px 8px; font-size: 11pt;"
            "  background-color: #d32f2f; color: white; }"
        )
        self._voice_button.setToolTip(tip)

    def _on_voice_released(self) -> None:
        """Voice button released — stop and process based on mode."""
        self._voice_button.setText("\U0001f3a4 Voice")
        self._voice_button.setStyleSheet("* { padding: 4px 8px; font-size: 11pt; }")

        if not self._recording or self._audio_source is None:
            return

        file_path = self._recording_file
        source = self._audio_source
        buf = self._audio_buf

        source.stop()
        buf.close()
        self._recording = False
        self._audio_source = None
        self._audio_buf = None

        raw_data = buf.data()
        if not raw_data:
            self._recording_file = ""
            return

        import wave
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(raw_data.data())

        if self._recording_mode == "direct":
            # Send audio data via RPC audio field, and add a [file: ...]
            # reference to the chat so the renderer shows a playable
            # audio element.  The RPC message is empty — the [file: ...]
            # text is only for display, sending it to the model would
            # confuse it into using read tool on the path.
            import base64
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            name = Path(file_path).name
            ref = f"[file: {file_path}]"
            # Always attach the recording reference so it's visible
            # in the chat as a playable audio element.
            self.chat.add_turn("human", f"\U0001f3a4 {ref}")
            self.chat_input.clear()

            if self._modalities and "audio" in self._modalities:
                self._bridge.submit_message(
                    "", audio=[{"type": "audio", "data": b64, "mimeType": "audio/wav"}]
                )
            else:
                self._bridge.submit_message(
                    f"\U0001f3a4 Voice recording attached: {ref}"
                )
        else:
            self._do_transcribe(file_path, self._settings.value("stt/model", "base"))

        self._recording_file = ""

    # ── theme definitions ───────────────────────────────────────

    _THEMES: dict[str, dict[str, str]] = {
        "dark": {
            "bg": "#1a1a2e",
            "text": "#e0e0e0",
            "bubble_user": "#2d2d44",
            "bubble_assistant": "#252535",
            "meta_text": "#888888",
            "border": "#444444",
        },
        "light": {
            "bg": "#f5f5f7",
            "text": "#000000",
            "bubble_user": "#e3f2fd",
            "bubble_assistant": "#ffffff",
            "meta_text": "#666666",
            "border": "#cccccc",
        },
    }

    # ── slots: display toggles ─────────────────────────────────

    def _on_toggle_thinking(self) -> None:
        val = self._show_thinking_btn.isChecked()
        self._show_thinking_btn.setText("Thinking ON" if val else "Thinking OFF")
        self.chat.set_show_thinking(val)

    def _on_toggle_tools(self) -> None:
        val = self._show_tools_btn.isChecked()
        self._show_tools_btn.setText("Tools ON" if val else "Tools OFF")
        self.chat.set_show_tools(val)

    # ── slots: system theme tracking ────────────────────────────

    def _on_system_theme_changed(self) -> None:
        """Re-apply the system theme when the OS switches dark/light mode."""
        pi_path = Path.home() / ".pi" / "agent" / "settings.json"
        try:
            pi = json.loads(pi_path.read_text())
            if pi.get("theme") != "system":
                return
        except (OSError, json.JSONDecodeError):
            return
        scheme = QApplication.instance().styleHints().colorScheme()
        tn = "dark" if scheme == Qt.ColorScheme.Dark else "light"
        tc = self._THEMES.get(tn)
        if tc:
            self.chat.set_theme(tc)

    # ── slots: settings dialog ──────────────────────────────────

    def _on_settings_dialog(self, default_tab: int = 0) -> None:
        """Show a unified settings dialog (Display + pi Backend).

        *default_tab* — which tab is shown first (0=Display, 1=pi Backend).
        """
        pi_path = Path.home() / ".pi" / "agent" / "settings.json"
        pi_settings: dict = {}
        try:
            pi_settings = json.loads(pi_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

        def _sr(label: str, cur: int, mn: int, mx: int) -> tuple[QHBoxLayout, QSpinBox]:
            """Build a labeled spin-row."""
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            sp = QSpinBox()
            sp.setRange(mn, mx)
            sp.setValue(cur)
            r.addWidget(sp)
            r.addStretch()
            return r, sp

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.resize(540, 420)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Display ────────────────────────────────────────
        disp = QWidget()
        dl = QVBoxLayout(disp)
        dl.setSpacing(8)

        theme_cb = QComboBox()
        theme_cb.addItems(["dark", "light", "system"])
        t = str(pi_settings.get("theme", "dark"))
        i = theme_cb.findText(t)
        if i >= 0: theme_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Theme:")); r.addWidget(theme_cb); r.addStretch()
        dl.addLayout(r)

        _, aw_spin = _sr("Auto-collapse agent work (keep N):",
                         self.chat._auto_collapse_agent_work, -1, 20)
        dl.addLayout(_sr("Auto-collapse agent work (keep N):",
                         self.chat._auto_collapse_agent_work, -1, 20)[0])
        _, tk_spin = _sr("Auto-collapse thinking (keep N):",
                         self.chat._auto_collapse_thinking, -1, 20)
        dl.addLayout(_sr("Auto-collapse thinking (keep N):",
                         self.chat._auto_collapse_thinking, -1, 20)[0])
        _, tl_spin = _sr("Auto-collapse tools (keep N):",
                         self.chat._auto_collapse_tools, -1, 20)
        dl.addLayout(_sr("Auto-collapse tools (keep N):",
                         self.chat._auto_collapse_tools, -1, 20)[0])
        dl.addSpacing(8)
        _, pg_spin = _sr("Messages per page:", self.chat._page_size, 1, 100)
        dl.addLayout(_sr("Messages per page:", self.chat._page_size, 1, 100)[0])
        _, pd_spin = _sr("Pages displayed:", self.chat._pages_displayed, 1, 10)
        dl.addLayout(_sr("Pages displayed:", self.chat._pages_displayed, 1, 10)[0])
        dl.addStretch()
        tabs.addTab(disp, "Display")

        # ── Tab 2: pi Backend ─────────────────────────────────────
        bk = QWidget()
        bl = QVBoxLayout(bk)
        bl.setSpacing(8)

        # Provider
        prov_cb = QComboBox(); prov_cb.setEditable(True)
        prov_cb.addItems(sorted(set(m.get("provider","") for m in self._available_models)))
        v = str(pi_settings.get("defaultProvider",""))
        if v: i=prov_cb.findText(v); prov_cb.setCurrentIndex(max(0,i))
        r = QHBoxLayout(); r.addWidget(QLabel("Default provider:")); r.addWidget(prov_cb,1); bl.addLayout(r)

        # Model
        mod_cb = QComboBox(); mod_cb.setEditable(True)
        mod_cb.addItems(sorted(set(m.get("id","") for m in self._available_models)))
        v = str(pi_settings.get("defaultModel",""))
        if v: i=mod_cb.findText(v); mod_cb.setCurrentIndex(max(0,i))
        r = QHBoxLayout(); r.addWidget(QLabel("Default model:")); r.addWidget(mod_cb,1); bl.addLayout(r)

        # Thinking level
        tl_cb = QComboBox()
        tl_cb.addItems(["off","minimal","low","medium","high","xhigh"])
        v = str(pi_settings.get("defaultThinkingLevel","low"))
        i = tl_cb.findText(v)
        if i >= 0: tl_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Default thinking level:")); r.addWidget(tl_cb); r.addStretch(); bl.addLayout(r)

        # Checkboxes
        hide_cb = QCheckBox("Hide thinking blocks")
        _s = QSettings("llm-thalamus", "llm-thalamus")
        _cur = int(_s.value("display/show_thinking", 1) or 1)
        hide_cb.setChecked(_cur != 1)
        bl.addWidget(hide_cb)
        quiet_cb = QCheckBox("Quiet startup (skip wake-up header)")
        quiet_cb.setChecked(bool(pi_settings.get("quietStartup",False)))
        bl.addWidget(quiet_cb)

        # Project trust
        trust_cb = QComboBox()
        trust_cb.addItems(["ask","always","never"])
        v = str(pi_settings.get("defaultProjectTrust","ask"))
        i = trust_cb.findText(v)
        if i >= 0: trust_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Default project trust:")); r.addWidget(trust_cb); r.addStretch(); bl.addLayout(r)

        bl.addSpacing(12)

        # Compaction group
        cg = QGroupBox("Compaction")
        cl = QVBoxLayout(cg)
        comp = pi_settings.get("compaction",{})
        comp_en = QCheckBox("Enable auto-compaction")
        comp_en.setChecked(bool(comp.get("enabled",True)))
        cl.addWidget(comp_en)
        _, cr_spin = _sr("Reserve tokens:", int(comp.get("reserveTokens",16384)), 1024, 131072)
        cl.addLayout(_sr("Reserve tokens:", int(comp.get("reserveTokens",16384)), 1024, 131072)[0])
        _, ck_spin = _sr("Keep recent tokens:", int(comp.get("keepRecentTokens",20000)), 1024, 262144)
        cl.addLayout(_sr("Keep recent tokens:", int(comp.get("keepRecentTokens",20000)), 1024, 262144)[0])
        bl.addWidget(cg)

        # Retry group
        rg = QGroupBox("Retry")
        rl = QVBoxLayout(rg)
        ret = pi_settings.get("retry",{})
        ret_en = QCheckBox("Enable auto-retry")
        ret_en.setChecked(bool(ret.get("enabled",True)))
        rl.addWidget(ret_en)
        _, rm_spin = _sr("Max retries:", int(ret.get("maxRetries",3)), 0, 10)
        rl.addLayout(_sr("Max retries:", int(ret.get("maxRetries",3)), 0, 10)[0])
        bl.addWidget(rg)

        # ── pi Config directory ──────────────────────────────────
        cfg_group = QGroupBox("pi Config")
        cfg_layout = QVBoxLayout(cfg_group)

        _local_cfg = str(
            Path(__file__).resolve().parent.parent.parent
            / "resources" / "pi-config"
        )
        _current_cfg = self._bridge._pi_config_dir or ""
        _initial_cfg = _current_cfg

        cfg_default = QRadioButton("Default (~/.pi/agent/)")
        cfg_local = QRadioButton("Local (shipped pi-config)")
        cfg_custom = QRadioButton("Custom:")
        cfg_custom_path = QLineEdit()
        cfg_custom_path.setPlaceholderText("/path/to/pi-config")
        cfg_browse = QPushButton("Browse...")

        if not _current_cfg or _current_cfg == _local_cfg:
            cfg_default.setChecked(not _current_cfg)
            cfg_local.setChecked(_current_cfg == _local_cfg)
        else:
            cfg_custom.setChecked(True)
            cfg_custom_path.setText(_current_cfg)

        cfg_layout.addWidget(cfg_default)
        cfg_layout.addWidget(cfg_local)
        custom_row = QHBoxLayout()
        custom_row.addWidget(cfg_custom)
        custom_row.addWidget(cfg_custom_path, 1)
        custom_row.addWidget(cfg_browse)
        cfg_layout.addLayout(custom_row)

        cfg_browse.clicked.connect(
            lambda: cfg_custom_path.setText(
                QFileDialog.getExistingDirectory(self, "Select pi config directory")
                or cfg_custom_path.text()
            )
        )

        def _cfg_value() -> str:
            if cfg_default.isChecked():
                return ""
            if cfg_local.isChecked():
                return _local_cfg
            return cfg_custom_path.text().strip()

        bl.addWidget(cfg_group)

        bl.addStretch()
        tabs.addTab(bk, "pi Backend")

        # ── Tab 3: Speech-to-Text ─────────────────────────────────
        stt_w = QWidget()
        stt_layout = QVBoxLayout(stt_w)
        stt_layout.setSpacing(8)

        # Backend discovery
        _stt_backends = available_backends()
        _stt_backend: SttBackend | None = None
        if _stt_backends:
            _stt_backend = get_backend(_stt_backends[0])

        _stt_available = _stt_backend is not None

        stt_status_label = QLabel()
        if _stt_available:
            stt_status_label.setText(
                f"Backend: {_stt_backend.name} (\u2713 available)"
            )
            stt_status_label.setStyleSheet("color: #4caf50;")
        else:
            stt_status_label.setText(
                "STT backend: not installed. "
                "Install python-faster-whisper to enable speech-to-text."
            )
            stt_status_label.setStyleSheet("color: #f44336;")
            stt_status_label.setWordWrap(True)
        stt_layout.addWidget(stt_status_label)

        if _stt_available:
            # ── Model row ────────────────────────────────────────
            model_row = QHBoxLayout()
            model_row.addWidget(QLabel("Model:"))

            stt_model_cb = QComboBox()
            stt_model_cb.addItems(_stt_backend.available_models())
            saved_model = _s.value("stt/model", "base")
            idx = stt_model_cb.findText(str(saved_model))
            if idx >= 0:
                stt_model_cb.setCurrentIndex(idx)
            model_row.addWidget(stt_model_cb, 1)

            stt_download_btn = QPushButton("Download")
            stt_delete_btn = QPushButton("Delete")
            stt_delete_btn.setEnabled(False)
            model_row.addWidget(stt_download_btn)
            model_row.addWidget(stt_delete_btn)
            stt_layout.addLayout(model_row)

            # ── Cache info ───────────────────────────────────────
            cache_group = QGroupBox("Model Cache")
            cache_layout = QVBoxLayout(cache_group)

            stt_cache_loc_label = QLabel()
            stt_cache_size_label = QLabel()
            stt_models_table = QLabel()
            stt_models_table.setWordWrap(True)
            stt_models_table.setTextFormat(Qt.TextFormat.PlainText)

            cache_layout.addWidget(stt_cache_loc_label)
            cache_layout.addWidget(stt_cache_size_label)
            cache_layout.addWidget(stt_models_table)
            stt_layout.addWidget(cache_group)

            # ── Recording mode ───────────────────────────────────
            rec_row = QHBoxLayout()
            rec_row.addWidget(QLabel("Recording mode:"))
            stt_rec_mode_cb = QComboBox()
            stt_rec_mode_cb.addItems(["Push-to-talk", "Dialog"])
            saved_mode = _s.value("stt/recording_mode", "Push-to-talk")
            idx2 = stt_rec_mode_cb.findText(str(saved_mode))
            if idx2 >= 0:
                stt_rec_mode_cb.setCurrentIndex(idx2)
            rec_row.addWidget(stt_rec_mode_cb)
            rec_row.addStretch()
            stt_layout.addLayout(rec_row)

            # ── Voice mode ────────────────────────────────────
            voice_row = QHBoxLayout()
            voice_row.addWidget(QLabel("Voice mode:"))
            stt_voice_cb = QComboBox()
            stt_voice_cb.addItems(["STT", "Direct"])
            saved_voice = _s.value("stt/voice_mode", "stt")
            iv = stt_voice_cb.findText(str(saved_voice).capitalize())
            if iv >= 0:
                stt_voice_cb.setCurrentIndex(iv)
            voice_row.addWidget(stt_voice_cb)
            voice_row.addStretch()
            stt_layout.addLayout(voice_row)

            # ── Task ──────────────────────────────────────────────
            task_row = QHBoxLayout()
            task_row.addWidget(QLabel("Task:"))
            stt_task_cb = QComboBox()
            stt_task_cb.addItems(["Transcribe", "Translate to English"])
            saved_task = _s.value("stt/task", "Transcribe")
            i3 = stt_task_cb.findText(str(saved_task))
            if i3 >= 0:
                stt_task_cb.setCurrentIndex(i3)
            task_row.addWidget(stt_task_cb)
            task_row.addStretch()
            stt_layout.addLayout(task_row)

            # ── Language ──────────────────────────────────────────
            lang_row = QHBoxLayout()
            lang_row.addWidget(QLabel("Language:"))
            stt_lang_cb = QComboBox()
            for code, label in _STT_LANGUAGES:
                stt_lang_cb.addItem(f"{label} ({code})" if code != "auto" else label, code)
            saved_lang = _s.value("stt/language", "auto")
            li = stt_lang_cb.findData(str(saved_lang))
            if li >= 0:
                stt_lang_cb.setCurrentIndex(li)
            stt_lang_cb.setToolTip(
                "Set the spoken language for better accuracy.\n"
                "'Auto-detect' lets Whisper guess the language.\n"
                "Picking the right language improves results, \n"
                "especially with smaller models."
            )
            lang_row.addWidget(stt_lang_cb)
            lang_row.addStretch()
            stt_layout.addLayout(lang_row)

            # ── Model info label ──────────────────────────────────
            stt_model_info_label = QLabel("")
            stt_model_info_label.setWordWrap(True)
            stt_model_info_label.setStyleSheet(
                "color: var(--meta-text, #888); font-size: 10px;"
                " padding: 4px 0;"
            )
            stt_layout.addWidget(stt_model_info_label)

            def _update_model_info() -> None:
                name = stt_model_cb.currentText()
                info = _STT_MODEL_INFO.get(name)
                if info:
                    stt_model_info_label.setText(
                        f"{name}: {info[0]} \u2014 {info[1]}"
                    )
                else:
                    stt_model_info_label.setText("")

            stt_model_cb.currentTextChanged.connect(_update_model_info)
            _update_model_info()

            # ── Populate cache info ──────────────────────────────
            def _refresh_stt_cache() -> None:
                if _stt_backend is None:
                    return
                info = _stt_backend.cache_info()
                stt_cache_loc_label.setText(f"Location: {info['location']}")
                stt_cache_size_label.setText(f"Total: {info['size_human']}")
                lines: list[str] = []
                for m in info["models"]:
                    status = (
                        f"{m['size_human']} cached"
                        if m["downloaded"]
                        else "not cached"
                    )
                    lines.append(f"  {m['name']:24s} \u2014 {status}")
                stt_models_table.setText("\n".join(lines))

                # Update download/delete buttons for current model.
                cur = stt_model_cb.currentText()
                downloaded = _stt_backend.is_model_downloaded(cur)
                stt_download_btn.setEnabled(not downloaded)
                stt_delete_btn.setEnabled(downloaded)

            _refresh_stt_cache()

            # ── Wire buttons ─────────────────────────────────────
            def _on_stt_model_changed() -> None:
                cur = stt_model_cb.currentText()
                if _stt_backend is None:
                    return
                downloaded = _stt_backend.is_model_downloaded(cur)
                stt_download_btn.setEnabled(not downloaded)
                stt_delete_btn.setEnabled(downloaded)

            stt_model_cb.currentTextChanged.connect(_on_stt_model_changed)

            def _on_stt_download() -> None:
                if _stt_backend is None:
                    return
                cur = stt_model_cb.currentText()
                stt_download_btn.setEnabled(False)
                stt_download_btn.setText("Downloading\u2026")
                QApplication.processEvents()
                try:
                    _stt_backend.download_model(cur)
                except Exception as exc:
                    QMessageBox.warning(
                        stt_w, "Download Error",
                        f"Failed to download model '{cur}':\n{exc}",
                    )
                finally:
                    stt_download_btn.setText("Download")
                    _refresh_stt_cache()

            stt_download_btn.clicked.connect(_on_stt_download)

            def _on_stt_delete() -> None:
                if _stt_backend is None:
                    return
                cur = stt_model_cb.currentText()
                reply = QMessageBox.question(
                    stt_w, "Delete Model",
                    f"Delete cached model '{cur}'?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                try:
                    _stt_backend.delete_model(cur)
                except Exception as exc:
                    QMessageBox.warning(
                        stt_w, "Delete Error",
                        f"Failed to delete model '{cur}':\n{exc}",
                    )
                _refresh_stt_cache()

            stt_delete_btn.clicked.connect(_on_stt_delete)

        stt_layout.addStretch()
        tabs.addTab(stt_w, "Speech-to-Text")
        tabs.setCurrentIndex(default_tab)

        # ── Buttons ───────────────────────────────────────────────
        br = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        close_btn = QPushButton("Close")
        br.addStretch(); br.addWidget(apply_btn); br.addWidget(close_btn)
        layout.addLayout(br)

        _config_changed = False
        _applied = False

        def _on_cfg_changed() -> None:
            nonlocal _config_changed
            _config_changed = (_cfg_value() != _initial_cfg)

        cfg_default.toggled.connect(_on_cfg_changed)
        cfg_local.toggled.connect(_on_cfg_changed)
        cfg_custom_path.textChanged.connect(_on_cfg_changed)

        def _apply() -> None:
            nonlocal _applied
            _applied = True

            self.chat.configure(
                page_size=pg_spin.value(),
                pages_displayed=pd_spin.value(),
                auto_collapse_agent_work=aw_spin.value(),
                auto_collapse_thinking=tk_spin.value(),
                auto_collapse_tools=tl_spin.value(),
            )
            tn = theme_cb.currentText()
            if tn == "system":
                scheme = QApplication.instance().styleHints().colorScheme()
                tn = "dark" if scheme == Qt.ColorScheme.Dark else "light"
            tc = self._THEMES.get(tn)
            if tc:
                self.chat.set_theme(tc)
            new_pi = dict(pi_settings)
            new_pi.update({
                "theme": tn,
                "defaultProvider": prov_cb.currentText(),
                "defaultModel": mod_cb.currentText(),
                "defaultThinkingLevel": tl_cb.currentText(),
                "hideThinkingBlock": hide_cb.isChecked(),
                "quietStartup": quiet_cb.isChecked(),
                "defaultProjectTrust": trust_cb.currentText(),
                "compaction": {
                    "enabled": comp_en.isChecked(),
                    "reserveTokens": cr_spin.value(),
                    "keepRecentTokens": ck_spin.value(),
                },
                "retry": {
                    "enabled": ret_en.isChecked(),
                    "maxRetries": rm_spin.value(),
                },
            })
            _s = QSettings("llm-thalamus", "llm-thalamus")
            _s.setValue("display/show_thinking", 0 if hide_cb.isChecked() else 1)
            # STT settings
            if _stt_available:
                _s.setValue("stt/model", stt_model_cb.currentText())
                _s.setValue("stt/recording_mode", stt_rec_mode_cb.currentText())
                _s.setValue("stt/voice_mode", stt_voice_cb.currentText().lower())
                _s.setValue("stt/task", stt_task_cb.currentText())
                _s.setValue("stt/language", stt_lang_cb.currentData())
            _s.sync()
            try:
                pi_path.write_text(json.dumps(new_pi, indent=2))
            except OSError:
                pass

            # Save config choice and restart if changed or on Backend tab
            cfg_val = _cfg_value()
            if cfg_val != _initial_cfg:
                self._bridge._pi_config_dir = cfg_val
                _s = QSettings("llm-thalamus", "llm-thalamus")
                _s.setValue("pi/config_dir", cfg_val)
                _s.sync()
            restart = tabs.currentIndex() == 1 or cfg_val != _initial_cfg
            if restart:
                self._on_reload()

        def _on_close() -> None:
            if _config_changed and not _applied:
                reply = QMessageBox.question(
                    dlg, "Apply changes?",
                    "The pi config directory has changed. Apply changes?\n"
                    "This will restart pi.",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    _apply()
            dlg.accept()

        apply_btn.clicked.connect(_apply)
        close_btn.clicked.connect(_on_close)
        dlg.exec()

    # ── slots: streaming ─────────────────────────────────────────

    def _on_stream_start(self) -> None:
        """A turn has started. Don't create the assistant bubble yet — it would
        appear empty during the thinking phase. The first ``text_delta`` in
        ``_on_stream_delta`` creates the bubble lazily."""
        pass

    def _on_stream_delta(self, text: str) -> None:
        if not self._streaming:
            self._streaming = True
            self.chat.begin_assistant_stream()
        self.chat.append_assistant_delta(text)

    def _on_stream_end(self) -> None:
        self._streaming = False
        self.chat.end_assistant_stream()

    # ── slots: thinking ──────────────────────────────────────────

    def _on_thinking_started(self) -> None:
        self.brain.set_saturation(0.7)
        self.chat.add_thinking()

    def _on_thinking_delta(self, text: str) -> None:
        self.chat.append_thinking_delta(text)

    def _on_thinking_finished(self) -> None:
        self.brain.set_saturation(1.0)
        self.chat.end_thinking()  # finalize, collapse

    # ── slots: tools ─────────────────────────────────────────────

    def _on_tool_start(self, call_id: str, name: str, args: dict) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_call",
            "tool_call_id": call_id,
            "tool_name": name,
            "args": args,
        })

    def _on_tool_update(self, call_id: str, partial_text: str) -> None:
        """Streaming progress from a running tool (e.g. subagent output)."""
        # Clean escaped JSON sequences so the text is readable.
        cleaned = partial_text.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", '"')
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_update",
            "tool_call_id": call_id,
            "partial_result": cleaned,
        })

    def _on_tool_end(self, call_id: str, name: str, result_text: str, is_error: bool, details: dict = None) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_result",
            "tool_call_id": call_id,
            "tool_name": name,
            "result": result_text,
            "ok": not is_error,
            "details": details,
        })

    # ── slots: lifecycle ─────────────────────────────────────────

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setEnabled(True)
        self.brain.set_state("llm" if busy else "thalamus")
        if not busy:
            self.follow_up_button.setEnabled(False)
            # Agent finished — refresh token / context stats.
            self._refresh_status_bar()

    def _on_input_text_changed(self) -> None:
        """Update the button label to reflect whether typing steers or aborts."""
        if self._busy:
            has_text = bool(self.chat_input.toPlainText().strip())
            self.send_button.setText("Steer" if has_text else "Stop")
            self.follow_up_button.setEnabled(has_text)

    def _on_escape(self) -> None:
        """Escape key: dismiss palette or abort the current agent operation."""
        if self._command_palette.is_visible:
            return
        if self._busy:
            self._bridge.send_command({"type": "abort"})

    def _on_error(self, text: str) -> None:
        self.chat.add_turn("system", text)
        self.brain.set_state("inactive")
        self._fix_corrupted_session(text)

    def _fix_corrupted_session(self, error_text: str) -> None:
        """If the last assistant message in the current session is empty
        (content: []), replace it with the error text so the session
        recovers rather than staying poisoned with an empty message.
        """
        if not self._current_session_path:
            return
        try:
            import json
            path = Path(self._current_session_path)
            if not path.exists():
                return
            lines = path.read_text().splitlines()
            changed = False
            for i in range(len(lines) - 1, -1, -1):
                try:
                    entry = json.loads(lines[i])
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "message":
                    continue
                msg = entry.get("message", {})
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", [])
                if not isinstance(content, list) or len(content) != 0:
                    continue
                # Found the last empty assistant message — replace with error.
                entry["message"]["content"] = [
                    {"type": "text", "text": f"[Error] {error_text}"}
                ]
                lines[i] = json.dumps(
                    entry, ensure_ascii=False, separators=(",", ":")
                )
                changed = True
                break
            if changed:
                path.write_text("\n".join(lines) + "\n")
                # Reload to reflect the fix.
                self._bridge.send_command({"type": "switch_session", "sessionPath": str(path)})
        except Exception as exc:
            print(f"[main_window] session fix failed: {exc}", file=__import__("sys").stderr)

    # ── slots: thinking level ─────────────────────────────────

    def _update_thinking_border(self) -> None:
        """Update the chat input border color based on current thinking level."""
        self.chat_input.set_thinking_border_color(self._thinking_level)

    def _on_cycle_thinking_level(self) -> None:
        """Cycle thinking level and refresh the UI."""
        self._bridge.send_command({"type": "cycle_thinking_level"})
        self._bridge.send_command({"type": "get_state"})

    def _on_thinking_level_menu(self) -> None:
        """Show a QMenu with available thinking levels."""
        levels = ["off", "minimal", "low", "medium", "high", "xhigh"]
        menu = QMenu(self)
        for level in levels:
            action = menu.addAction(level)
            action.setCheckable(True)
            if level == self._thinking_level:
                action.setChecked(True)
        chosen = menu.exec(self._thinking_label.mapToGlobal(
            self._thinking_label.rect().bottomLeft()))
        if chosen is not None:
            self._thinking_level = chosen.text()
            self._thinking_label.setText(chosen.text())
            self._update_thinking_border()
            self._bridge.send_command({
                "type": "set_thinking_level",
                "level": chosen.text(),
            })

    # ── slots: session management ──────────────────────────────

    def _on_open_session_dialog(self) -> None:
        """Create (or show) the non‑modal session manager dialog."""
        if self._session_dialog is None:
            dlg = SessionDialog(self)
            dlg.new_requested.connect(self._on_new_session)
            dlg.reload_requested.connect(self._on_reload)
            dlg.compact_requested.connect(self._on_compact)
            dlg.import_requested.connect(self._on_import_session)
            dlg.session_info_requested.connect(self._on_session_info)
            dlg.switch_requested.connect(self._on_switch_session)
            dlg.rename_requested.connect(self._on_rename_session)
            dlg.delete_requested.connect(self._on_delete_session)
            dlg.inspect_requested.connect(self._on_inspect_session)
            self._session_dialog = dlg

        dlg = self._session_dialog
        # Refresh the tree with latest data.
        dlg.refresh_sessions(
            str(self._session_dir()) if self._session_dir() else None,
            self._current_session_path,
        )
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_import_session(self) -> None:
        """Open a file dialog and switch to the selected .jsonl session."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Session",
            str(Path.home() / ".pi" / "agent" / "sessions"),
            "Session files (*.jsonl)",
        )
        if not path:
            return
        self._bridge.send_command({
            "type": "switch_session",
            "sessionPath": path,
        })

    def _on_session_info(self) -> None:
        """Show current session info in a message box."""
        # Request latest state + stats and show once both arrive.
        self._bridge.send_command({"type": "get_state"})
        self._bridge.send_command({"type": "get_session_stats"})

        # We'll accumulate the results and show them via a helper.
        self._pending_session_info: dict[str, object] = {}

        def _on_info_get_state(data: dict) -> None:
            self._pending_session_info["sessionFile"] = data.get("sessionFile", "?")
            self._pending_session_info["sessionId"] = data.get("sessionId", "?")
            self._pending_session_info["sessionName"] = data.get("sessionName") or "(unnamed)"
            self._pending_session_info["messageCount"] = data.get("messageCount", "?")
            model = data.get("model")
            if isinstance(model, dict):
                self._pending_session_info["model"] = f"{model.get('provider','?')}/{model.get('name',model.get('id','?'))}"
            self._pending_session_info["thinkingLevel"] = data.get("thinkingLevel", "-")
            self._pending_session_info["cwd"] = str(Path.cwd())
            self._maybe_show_session_info()

        def _on_info_stats(data: dict) -> None:
            tokens = data.get("tokens", {})
            if isinstance(tokens, dict):
                parts: list[str] = []
                for label, key in [("Input", "input"), ("Output", "output"),
                                    ("Cache Read", "cacheRead"), ("Cache Write", "cacheWrite")]:
                    v = int(tokens.get(key, 0) or 0)
                    if v:
                        parts.append(f"{label}: {_fmt_tokens(v)}")
                self._pending_session_info["tokens"] = ", ".join(parts) if parts else "none"
            cost = data.get("cost", 0)
            if cost:
                self._pending_session_info["cost"] = f"${float(cost):.4f}"
            ctx = data.get("contextUsage", {})
            if isinstance(ctx, dict):
                pct = ctx.get("percent")
                if pct is not None:
                    self._pending_session_info["context"] = f"{float(pct):.0f}% ({ctx.get('tokens','?')}/{ctx.get('contextWindow','?')})"
            self._pending_session_info["userMessages"] = data.get("userMessages", "?")
            self._maybe_show_session_info()

        # Store the callbacks on the instance so the response handler can find them.
        self._on_info_get_state = _on_info_get_state
        self._on_info_stats = _on_info_stats

    def _maybe_show_session_info(self) -> None:
        """Show the session info dialog if both state and stats have arrived."""
        info = self._pending_session_info
        # Both get_state and get_session_stats provide at least some fragment.
        if "sessionFile" in info and "tokens" in info:
            msg_parts: list[str] = []
            for label, key in [
                ("Session file", "sessionFile"),
                ("Session ID", "sessionId"),
                ("Session name", "sessionName"),
                ("Working directory", "cwd"),
                ("Messages", "messageCount"),
                ("Model", "model"),
                ("Thinking level", "thinkingLevel"),
                ("Token usage", "tokens"),
            ]:
                v = info.get(key)
                if v is not None:
                    msg_parts.append(f"{label}: {v}")
            if "cost" in info:
                msg_parts.append(f"Cost: {info['cost']}")
            if "context" in info:
                msg_parts.append(f"Context: {info['context']}")

            QMessageBox.information(
                self,
                f"Session: {info.get('sessionName', '?')}",
                "\n".join(msg_parts),
            )
            # Clean up.
            self._pending_session_info = {}

    def _on_new_session(self) -> None:
        """Ask the user where to start a fresh session.

        Pops up a native directory picker.  If a directory different from
        the current CWD is chosen, pi is restarted from that location because
        pi's CWD is fixed at process launch.
        """
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select working directory for new session",
            str(Path.cwd()),
        )
        if not dir_path:
            return  # user cancelled

        target = Path(dir_path).resolve()
        if target == Path.cwd().resolve():
            # Same directory — just start a new session via RPC.
            self._bridge.send_command({"type": "new_session"})
        else:
            # Different directory — restart pi from the new CWD.
            self._bridge.restart(cwd=str(target))
            self.chat.clear()
            self._current_session_path = None
            self._refresh_session_list()
            QTimer.singleShot(1200, self._refresh_status_bar)
            # Give pi a moment to start, then request a fresh session.
            QTimer.singleShot(1800, lambda: self._bridge.send_command({"type": "new_session"}))

    # More shortcuts handled natively by widgets (added to help below).
    _HELP_SHORTCUTS: dict[str, str] = {
        "Enter":         "Send message",
        "Shift+Enter":   "New line in input",
        "Alt+Enter":     "Queue follow-up message",
        "Ctrl+Scroll":   "Zoom chat",
        "Up/Down":       "Navigate command palette",
        "Tab":           "Execute selected command",
    }

    def _on_show_hotkeys(self) -> None:
        """Show a dialog listing all keyboard shortcuts."""
        all_keys = {
            **self._shortcut_descriptions,
            **self._HELP_SHORTCUTS,
        }
        lines = ["Keyboard shortcuts:", ""]
        width = max(len(k) for k in all_keys)
        for key, desc in all_keys.items():
            lines.append(f"{key:<{width}}  {desc}")
        QMessageBox.information(self, "Keyboard Shortcuts", "\n".join(lines))

    def _on_copy_last(self) -> None:
        """Copy the last assistant message to clipboard."""
        for msg in reversed(self.chat._messages):
            if msg.get("kind") == "turn" and msg.get("role") == "you":
                text = msg.get("content", "")
                if text:
                    QApplication.clipboard().setText(text)
                break

    def _on_compact(self) -> None:
        """Send the compact RPC to compress context."""
        self._bridge.send_command({"type": "compact"})

    def _on_reload(self) -> None:
        """Restart the pi subprocess to pick up new extensions, skills,
        and configuration, then resume the current session."""
        self._bridge.restart(
            cwd=str(Path.cwd()),
            session_path=self._current_session_path,
        )
        self.chat.clear()
        self._refresh_session_list()
        # Give pi time to start up and load the session, then fetch
        # history + state.
        QTimer.singleShot(1500, self._bridge.load_history)
        QTimer.singleShot(2000, self._refresh_status_bar)

    def _on_switch_session(self, session_path: str) -> None:
        """Switch to a different session and reload conversation."""
        self._bridge.send_command({
            "type": "switch_session",
            "sessionPath": session_path,
        })

    def _on_inspect_session(self, session_path: str) -> None:
        """Open a read-only dialog showing the session's messages."""
        from ui.chat_renderer import ChatRenderer

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Inspect: {Path(session_path).stem[:40]}")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)

        viewer = ChatRenderer()

        # Stacked widget: index 0 = native placeholder (instant), index 1 = viewer.
        # Switch to the viewer once the WebEngine-heavy render completes.
        from PySide6.QtWidgets import QStackedWidget
        stack = QStackedWidget()

        placeholder = QLabel("Rendering session…")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(
            "color: #888; font-size: 14pt;"
            "background: transparent;"
        )
        stack.addWidget(placeholder)  # index 0
        stack.addWidget(viewer)        # index 1
        stack.setCurrentIndex(0)
        layout.addWidget(stack, 1)

        btn_row = QHBoxLayout()
        switch_btn = QPushButton("Switch to this session")
        switch_btn.clicked.connect(lambda: (
            self._on_switch_session(session_path),
            dlg.accept(),
        ))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(switch_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Show the dialog immediately (placeholder QLabel is native Qt, renders
        # instantly), then populate asynchronously so the WebEngine-heavy
        # rendering doesn't block the UI.
        dlg.show()
        QTimer.singleShot(
            0, lambda: self._populate_inspect(viewer, session_path, dlg, stack)
        )
        dlg.exec()

    def _populate_inspect(
        self,
        viewer: "ChatRenderer",
        session_path: str,
        dlg: QDialog,
        stack: "QStackedWidget | None" = None,
    ) -> None:
        """Parse and render a session file into an already-visible dialog."""
        try:
            viewer.begin_batch()
            with open(session_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {}) if isinstance(entry, dict) else None
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = []
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                parts.append(b.get("text", ""))
                        text = " ".join(parts)
                    else:
                        text = str(content) if content else ""
                    if not text:
                        continue
                    display_role = "human" if role == "user" else "you"
                    viewer.add_turn(display_role, text)
            viewer.end_batch()
            if stack is not None:
                stack.setCurrentIndex(1)
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.warning(dlg, "Error", f"Failed to read session:\n{e}")

    def _on_command_requested(self, name: str, remaining: str) -> None:
        """Handle a slash command that needs UI interaction.

        Currently supports:
          - /name  → opens the rename dialog
          - /compact → compact context RPC
          - /new   → opens directory picker (same as Session → New)
          - /export → calls export_html RPC directly
        """
        if name == "name":
            session_path = self._current_session_path
            if session_path:
                current_name = remaining if remaining else ""
                new_name, ok = QInputDialog.getText(
                    self, "Set Session Name", "New name:",
                    text=current_name,
                )
                if ok and new_name:
                    self._bridge.send_command({
                        "type": "set_session_name",
                        "name": new_name,
                    })
        elif name in ("model", "scoped-models"):
            self._on_open_model_picker()
        elif name == "session":
            self._on_session_info()
        elif name in ("resume", "tree", "import"):
            self._on_open_session_dialog()
        elif name == "settings":
            self._on_settings_dialog(1)
        elif name == "quit":
            self.close()
        elif name == "hotkeys":
            self._on_show_hotkeys()
        elif name == "copy":
            self._on_copy_last()
        elif name == "reload":
            self._on_reload()
        elif name == "compact":
            self._on_compact()
        elif name == "new":
            self._on_new_session()
        elif name == "export":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Session",
                str(Path.home() / "session.html"),
                "HTML files (*.html);;All files (*)",
            )
            if path:
                self._bridge.send_command({
                    "type": "export_html",
                    "outputPath": path,
                })
            else:
                # No path — pi uses a default location.
                self._bridge.send_command({"type": "export_html"})

    def _on_rename_session(self, session_path: str, new_name: str) -> None:
        """Set the display name for a session."""
        if session_path == self._current_session_path:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": new_name,
            })
        else:
            # Switch first, then rename on the response handler.
            self._pending_rename = new_name
            self._bridge.send_command({
                "type": "switch_session",
                "sessionPath": session_path,
            })

    def _on_delete_session(self, paths: list[str]) -> None:
        """Delete one or more session files from disk."""
        failed: list[str] = []
        for session_path in paths:
            try:
                p = Path(session_path)
                if p.exists():
                    p.unlink()
            except OSError as e:
                failed.append(f"{Path(session_path).name}: {e}")
        self._refresh_session_list()
        if failed:
            QMessageBox.warning(
                self, "Error",
                f"Failed to delete {len(failed)} session(s):\n"
                + "\n".join(failed[:5])
            )

    def _on_session_switched(self) -> None:
        """Called after new_session or switch_session succeeds.

        Clears the chat, reloads history, and refreshes the
        session list.
        """
        self.chat.clear()
        self._bridge.load_history()
        self._refresh_session_list()
        self._refresh_status_bar()

        # If a rename was queued before the switch, send it now.
        if self._pending_rename:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": self._pending_rename,
            })
            self._pending_rename = None

    def _session_dir(self) -> Path | None:
        """Resolve the pi session storage directory.

        Returns None if we can't determine the location.
        """
        if self._session_dir_path is not None:
            return self._session_dir_path
        cfg = self._bridge._pi_config_dir
        if cfg:
            self._session_dir_path = Path(cfg) / "sessions"
        else:
            self._session_dir_path = Path.home() / ".pi" / "agent" / "sessions"
        if not self._session_dir_path.is_dir():
            self._session_dir_path = None
        return self._session_dir_path

    def _refresh_session_list(self) -> None:
        """Re-scan the session directory and update the session dialog tree.

        Only refreshes if the dialog is currently visible.
        """
        dlg = self._session_dialog
        if dlg is not None and dlg.isVisible():
            dlg.refresh_sessions(
                str(self._session_dir()) if self._session_dir() else None,
                self._current_session_path,
            )

    # ── slots: model picker ──────────────────────────────────

    def _on_open_model_picker(self) -> None:
        """Open the model picker dialog and send ``set_model`` on accept."""
        if not self._available_models:
            # Models not loaded yet — request and defer.
            self._bridge.send_command({"type": "get_available_models"})
            QMessageBox.information(
                self,
                "Model Picker",
                "Model list is being loaded.  Please try again in a moment.",
            )
            return

        scoped_raw = self._settings.value("model/scoped_ids")
        scoped_ids: set[str] = (
            set(json.loads(scoped_raw))
            if isinstance(scoped_raw, str)
            else set()
        )

        dlg = ModelPickerDialog(self._available_models, scoped_ids, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.selected_model_id and dlg.selected_provider:
                self._bridge.send_command({
                    "type": "set_model",
                    "provider": dlg.selected_provider,
                    "modelId": dlg.selected_model_id,
                })
            self._settings.setValue(
                "model/scoped_ids",
                json.dumps(sorted(dlg.scoped_ids)),
            )
            self._settings.sync()

    # ── slots: session management ──────────────────────────────

    def _on_get_state(self, data: dict) -> None:
        """Handle ``get_state`` response — update model and session info."""
        # Update current session path.
        session_file = data.get("sessionFile")
        if session_file:
            self._current_session_path = str(session_file)
            dlg = self._session_dialog
            if dlg is not None and dlg.isVisible():
                dlg.set_current_session(self._current_session_path)

        # Update model label.
        model = data.get("model")
        if isinstance(model, dict):
            self._provider = str(model.get("provider", ""))
            thinking_level = str(data.get("thinkingLevel", ""))
            self._thinking_level = thinking_level
            self._update_thinking_border()
            model_name = model.get("name") or model.get("id") or "?"
            parts: list[str] = []
            if self._provider:
                parts.append(f"({self._provider})")
            parts.append(model_name)
            self._model_label.setText(" ".join(parts))
            self._thinking_label.setText(thinking_level if thinking_level else "-")

            # Update modality indicators from config (baseline)
            model_input = model.get("input", ["text"])
            self._modalities = list(model_input) if isinstance(model_input, list) else []
            self._update_modality_icons()

            # Query backend for authoritative modality info
            base_url = model.get("baseUrl", "")
            model_id = model.get("id", "")
            if base_url and model_id:
                self._query_backend_capabilities(base_url, model_id)

    # ── model capability queries ────────────────────────────────

    def _update_modality_icons(self) -> None:
        """Set icon text based on model capabilities.

        Empty text hides the icon; the emoji shows it.  This is more
        reliable than setVisible() across Qt/emoji combinations.
        """
        self._vision_icon.setText("\U0001f441\ufe0f" if "image" in self._modalities else "")
        self._audio_icon.setText("\U0001f3a4" if "audio" in self._modalities else "")

    def _query_backend_capabilities(self, base_url: str, model_id: str) -> None:
        """Query the model backend's /v1/models endpoint for authoritative
        capability info (input_modalities).  Only known to work with
        llama.cpp; other providers are skipped.

        Queries synchronously — for a local backend this is < 50 ms.
        """
        import json, urllib.request

        url = base_url.rstrip("/") + "/models"
        if "localhost" not in url and "127.0.0.1" not in url:
            return

        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
        except (OSError, json.JSONDecodeError, ValueError):
            return

        for entry in data.get("data", []):
            if entry.get("id") == model_id:
                arch = entry.get("architecture", {})
                modalities = arch.get("input_modalities", [])
                if isinstance(modalities, list):
                    merged = list(self._modalities)
                    changed = False
                    for m in modalities:
                        if m not in merged:
                            merged.append(m)
                            changed = True
                    if changed:
                        self._modalities = merged
                        self._update_modality_icons()
                break

    def _on_history_turn(self, role: str, content: str, _ts: str) -> None:
        # Map pi roles to chat renderer roles.
        # pi roles: "user", "assistant", "toolResult", "bashExecution"
        display_role = "human" if role == "user" else "you"
        self.chat.begin_batch()
        self.chat.add_turn(display_role, content)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _on_history_thinking(self, text: str, _ts: str) -> None:
        # History thinking bubbles start collapsed.
        self.chat.begin_batch()
        self.chat.add_thinking(text)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _flush_history_batch(self) -> None:
        """Render all accumulated history messages in one shot."""
        self._history_batch_pending = False
        self.chat.end_batch()

    # ── slots: extension UI ───────────────────────────────────────

    def _on_extension_ui_dialog(
        self, request_id: str, method: str, title: str, data: dict
    ) -> None:
        """Show a Qt dialog for a pi ``extension_ui_request`` and send the
        response back through the bridge."""
        response: dict

        if method == "confirm":
            message = str(data.get("message", ""))
            reply = QMessageBox.question(
                self, title, message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            response = {"confirmed": reply == QMessageBox.StandardButton.Yes}

        elif method == "select":
            options_raw = data.get("options", [])
            options = (
                [str(o) for o in options_raw]
                if isinstance(options_raw, list) else []
            )
            item, ok = QInputDialog.getItem(
                self, title, "Choose:", options, 0, False,
            )
            if ok:
                response = {"value": item}
            else:
                response = {"cancelled": True}

        elif method == "input":
            placeholder = str(data.get("placeholder", ""))
            text, ok = QInputDialog.getText(self, title, placeholder)
            if ok:
                response = {"value": text}
            else:
                response = {"cancelled": True}

        elif method == "editor":
            prefill = str(data.get("prefill", ""))
            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            dlg.resize(500, 400)
            layout = QVBoxLayout(dlg)
            editor = QTextEdit()
            editor.setPlainText(prefill)
            layout.addWidget(editor)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
            )
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                response = {"value": editor.toPlainText()}
            else:
                response = {"cancelled": True}

        else:
            return  # unknown method, don't respond

        self._bridge.send_extension_ui_response(request_id, response)

    def _on_extension_ui_notify(self, message: str, notify_type: str) -> None:
        # Log to stderr for now; future: status bar or toast.
        print(
            f"[notify] [{notify_type}] {message}",
            flush=True,
        )

    def _on_extension_ui_status(self, key: str, text: str) -> None:
        """Handle a setStatus extension_ui_request.

        When *text* is non-empty, store/update the entry for *key*.
        When *text* is empty, remove the entry (status was cleared).
        """
        if text:
            self._status_entries[key] = text
        else:
            self._status_entries.pop(key, None)
        self._update_status_extras()

    def _update_status_extras(self) -> None:
        """Rebuild the status extras label from current entries.

        Shows all non-empty status lines joined with spaces on a second
        row of the status bar.  Hidden when there are no entries.
        """
        parts = [v for v in self._status_entries.values() if v]
        if not parts:
            self._status_extras_label.setVisible(False)
            return
        self._status_extras_label.setText("    ".join(parts))
        self._status_extras_label.setVisible(True)

    # ── slots: status bar ────────────────────────────────────────

    def _on_response_received(self, command: str, response: object) -> None:
        """Route RPC responses to the appropriate handler."""
        if not isinstance(response, dict):
            return
        if not response.get("success"):
            # Graceful error handling for failed commands (e.g., sending
            # audio/image to a model that doesn't support it). Show the
            # error in the chat and reset busy state so the user can
            # continue.
            if command in ("prompt", "steer", "follow_up"):
                err = response.get("error", "Command failed")
                # Truncate verbose API errors to the first line
                summary = err.split("\n")[0][:300]
                self.chat.add_turn("system", f"\u26a0\ufe0f {summary}")
                self._on_busy(False)
            return
        data = response.get("data")
        if not isinstance(data, dict):
            return

        if command == "get_state":
            if hasattr(self, "_on_info_get_state"):
                self._on_info_get_state(data)
                del self._on_info_get_state
                return  # Don't double-handle
            self._on_get_state(data)
        elif command == "get_available_models":
            models = data.get("models", [])
            if isinstance(models, list):
                self._available_models = models
        elif command == "set_model":
            self._refresh_status_bar()
        elif command == "cycle_model":
            self._refresh_status_bar()
        elif command == "get_commands":
            cmds = data.get("commands", [])
            if isinstance(cmds, list):
                self._command_palette.set_dynamic_commands(cmds)
        elif command == "new_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "switch_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "set_session_name":
            self._refresh_session_list()
        elif command == "clone":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "get_session_stats":
            if hasattr(self, "_on_info_stats"):
                self._on_info_stats(data)
                del self._on_info_stats
                return
            tokens = data.get("tokens")
            if isinstance(tokens, dict):
                inp = int(tokens.get("input", 0) or 0)
                out = int(tokens.get("output", 0) or 0)
                cache = int(tokens.get("cacheRead", 0) or 0)
                parts: list[str] = []
                if inp:
                    parts.append(f"↑{_fmt_tokens(inp)}")
                if out:
                    parts.append(f"↓{_fmt_tokens(out)}")
                if cache:
                    parts.append(f"R{_fmt_tokens(cache)}")
                if parts:
                    self._tokens_label.setText(" ".join(parts))
                else:
                    self._tokens_label.setText("\u00a0")
            ctx = data.get("contextUsage")
            if isinstance(ctx, dict) and ctx.get("contextWindow"):
                pct = ctx.get("percent")
                if pct is not None:
                    self._context_label.setText(f"{float(pct):.0f}%")
                else:
                    self._context_label.setText("\u00a0")
            else:
                self._context_label.setText("\u00a0")

    def _refresh_status_bar(self) -> None:
        """Request fresh state and stats from pi; update local info."""
        self._update_path_label()
        self._refresh_session_list()
        self._bridge.send_command({"type": "get_state"})
        self._bridge.send_command({"type": "get_session_stats"})
        self._bridge.send_command({"type": "get_commands"})
        self._bridge.send_command({"type": "get_available_models"})

    def _update_path_label(self) -> None:
        """Update the path label with shortened cwd and optional git branch."""
        cwd = Path.cwd()
        home = Path.home()
        try:
            short = f"~/{cwd.relative_to(home)}" if cwd.is_relative_to(home) else str(cwd)
        except ValueError:
            short = str(cwd)
        branch = _git_branch(cwd)
        if branch:
            self._path_label.setText(f"{short} ({branch})")
        else:
            self._path_label.setText(short)

    def _collect_sidebar_audio(self) -> list[dict] | None:
        """Scan sidebar attachments for audio files and return RPC-compatible dicts.

        Each dict: ``{"type": "audio", "data": base64, "mimeType": "..."}``
        Images are NOT sent via RPC — the model uses the `read` tool
        to load them from the [file: /path] reference in the text.
        """
        import base64
        _EXTS = frozenset({".wav", ".mp3", ".ogg", ".flac", ".m4a"})
        _MIME = {
            ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
            ".flac": "audio/flac", ".m4a": "audio/mp4",
        }

        audio: list[dict] = []
        for item in self.chat_input.sidebar._items:
            ext = Path(item["path"]).suffix.lower()
            mime = _MIME.get(ext)
            if mime is None:
                continue
            try:
                with open(item["path"], "rb") as f:
                    data = base64.b64encode(f.read()).decode()
            except OSError:
                continue
            audio.append({"type": "audio", "data": data, "mimeType": mime})

        return audio if audio else None


# ── helpers ──────────────────────────────────────────────────────────


def _git_branch(cwd: Path) -> str:
    """Return the current git branch name, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=2,
        )
        branch = result.stdout.strip()
        if result.returncode == 0 and branch and branch != "HEAD":
            return branch
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return ""


def _fmt_tokens(count: int) -> str:
    """Format a token count with k / M suffix."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)
