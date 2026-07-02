"""VoiceController — manages microphone capture, STT, and Direct-mode audio.

Handles the full lifecycle: hold-to-record → release → transcribe (STT mode)
or send raw audio (Direct mode).  Emits signals for the results; the parent
(MainWindow) decides what to display and how to send.
"""

from __future__ import annotations

import base64
import os
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, QTimer, Signal
from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices
from PySide6.QtWidgets import QApplication, QMessageBox

from controller.stt import SttBackend, model_size_human


# ── Worker for background model downloads ───────────────────────


class _DownloadWorker(QObject):
    """Downloads an STT model in a background thread."""

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


# ── VoiceController ────────────────────────────────────────────


class VoiceController(QObject):
    """Manages the voice recording button lifecycle.

    Signals:
        transcription_ready(str):  Transcribed text (STT mode).
        audio_ready(str, str):     (file_path, base64_data) for Direct mode.
        error(str):                Error message.

    Constructor args:
        voice_button:     QPushButton that fires pressed/released.
        stt_backend:      STT backend instance, or None.
        chat_input:       QPlainTextEdit-like widget for inserting text.
        attach_dir:       Path to directory for saving recordings.
        parent:           QObject parent.
    """

    transcription_ready = Signal(str)    # text
    audio_ready = Signal(str, str)       # file_path, base64_data
    error = Signal(str)

    def __init__(
        self,
        voice_button,
        stt_backend: SttBackend | None,
        chat_input,
        attach_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._stt_backend = stt_backend
        self._chat_input = chat_input
        self._settings = QSettings("llm-thalamus", "llm-thalamus")
        self._attach_dir = attach_dir

        # ── recording state ────────────────────────────────────
        self._recording: bool = False
        self._recording_mode: str = self._settings.value("stt/voice_mode", "stt")
        self._audio_source: QAudioSource | None = None
        self._audio_buf = None
        self._audio_format: QAudioFormat | None = None
        self._recording_file: str = ""

        # ── wire button ────────────────────────────────────────
        self._btn = voice_button
        self._btn.pressed.connect(self._on_pressed)
        self._btn.released.connect(self._on_released)
        self._btn.setText("\U0001f3a4 STT" if self._recording_mode == "stt" else "\U0001f3a4 Voice")

    # ── recording lifecycle ─────────────────────────────────────

    def _start_recording(self, out_path: str) -> None:
        """Begin audio capture to *out_path* WAV file."""
        if self._recording:
            return

        device = QMediaDevices().defaultAudioInput()

        afmt = QAudioFormat()
        afmt.setSampleRate(16000)
        afmt.setChannelCount(1)
        afmt.setSampleFormat(QAudioFormat.Int16)

        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)

        source = QAudioSource(device, afmt)

        self._audio_buf = buf
        self._audio_source = source
        self._audio_format = afmt
        self._recording_file = out_path
        self._recording = True

        source.start(buf)

    def _on_pressed(self) -> None:
        """Voice button pressed — start recording."""
        from PySide6.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd_hh-mm-ss")
        mode = self._settings.value("stt/voice_mode", "stt")
        self._recording_mode = mode

        if mode == "direct":
            out_path = str(self._attach_dir / f"recording-{ts}.wav")
            tip = "Recording\u2026 release to send"
        else:
            out_path = f"/tmp/llm-thalamus-recording-{ts}.wav"
            tip = "Recording\u2026 release to transcribe"

        self._start_recording(out_path)
        self._btn.setText("\U0001f3a4 \u25a0")
        self._btn.setStyleSheet(
            "* { padding: 4px 8px; font-size: 11pt;"
            "  background-color: #d32f2f; color: white; }"
        )
        self._btn.setToolTip(tip)

    def _on_released(self) -> None:
        """Voice button released — stop and process based on mode."""
        self._btn.setText("\U0001f3a4 Voice")
        self._btn.setStyleSheet("* { padding: 4px 8px; font-size: 11pt; }")

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

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(raw_data.data())

        if self._recording_mode == "direct":
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            self.audio_ready.emit(file_path, b64)
        else:
            self._transcribe_file(file_path)

        self._recording_file = ""

    # ── STT pipeline ──────────────────────────────────────────

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
        """Download *model*, then transcribe *file_path*."""
        from PySide6.QtWidgets import QProgressDialog

        size_hint = model_size_human(model)
        label = f"Downloading model '{model}' {size_hint}\n"
        label += "First-time download from HuggingFace Hub."

        dlg = QProgressDialog(label, None, 0, 0, self.parent())
        dlg.setWindowTitle("STT Model Download")
        dlg.setMinimumDuration(0)
        dlg.show()
        QApplication.processEvents()

        thread = QThread(self)
        worker = _DownloadWorker(self._stt_backend, model)
        worker.moveToThread(thread)

        def _on_done(m: str) -> None:
            dlg.close()
            thread.quit()
            if thread.isRunning():
                thread.wait(3000)
            self._do_transcribe(file_path, m)

        def _on_error(err: str) -> None:
            dlg.close()
            thread.quit()
            if thread.isRunning():
                thread.wait(3000)
            QMessageBox.warning(
                self.parent(), "Download Error",
                f"Failed to download STT model '{model}':\n{err}",
            )

        worker.finished.connect(_on_done)
        worker.error.connect(_on_error)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.start()

    def _do_transcribe(self, file_path: str, model: str) -> None:
        """Transcribe *file_path* using *model* and emit result."""
        task_raw = self._settings.value("stt/task", "Transcribe")
        task = "translate" if str(task_raw) == "Translate to English" else "transcribe"
        lang_raw = self._settings.value("stt/language", "auto")
        lang = str(lang_raw) if lang_raw and str(lang_raw) != "auto" else None

        self._btn.setText("\U0001f3a4 \u2026")
        self._btn.setToolTip("Transcribing\u2026")
        QApplication.processEvents()

        try:
            text = self._stt_backend.transcribe(
                file_path, model=model, task=task, language=lang,
            )
        except Exception as exc:
            self._btn.setText("\U0001f3a4 STT")
            self._btn.setToolTip("Hold to record, release to process")
            try:
                os.unlink(file_path)
            except OSError:
                pass
            self.error.emit(str(exc))
            return

        self._btn.setText("\U0001f3a4 STT")
        self._btn.setToolTip("Hold to record, release to process")
        try:
            os.unlink(file_path)
        except OSError:
            pass

        if text:
            self.transcription_ready.emit(text)
