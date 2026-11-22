"""Tests for the recorded-audio cleanup in VoiceController.

Recording writes a WAV into the attachments directory.  Whatever happens next —
transcribed, or the model refusing — that file must not be left behind, or every
dictation leaves a stray recording on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


class _Backend:
    """Minimal STT backend: reports the model as present, never transcribes."""

    def __init__(self, text: str = "hello", error: Exception | None = None):
        self._text = text
        self._error = error
        self.seen: list[str] = []

    def is_model_downloaded(self, model: str) -> bool:
        return True

    def transcribe(self, audio_path: str, **_kwargs) -> str:
        self.seen.append(audio_path)
        if self._error:
            raise self._error
        return self._text


def _controller(qapp, backend, tmp_path: Path):
    from PySide6.QtWidgets import QPlainTextEdit, QPushButton

    from ui.voice_controller import VoiceController

    return VoiceController(
        voice_button=QPushButton("voice"),
        stt_backend=backend,
        chat_input=QPlainTextEdit(),
        attach_dir=tmp_path,
    )


def _wav(tmp_path: Path) -> Path:
    path = tmp_path / "recording.wav"
    path.write_bytes(b"RIFF....WAVEfmt ")
    return path


class TestTranscribedAudioCleanup:
    def test_file_is_removed_after_transcription(self, qapp, tmp_path):
        backend = _Backend(text="hello")
        controller = _controller(qapp, backend, tmp_path)
        audio = _wav(tmp_path)
        heard: list[str] = []
        controller.transcription_ready.connect(heard.append)

        controller._transcribe_file(str(audio))

        assert backend.seen == [str(audio)]
        assert heard == ["hello"]
        assert not audio.exists()

    def test_file_is_removed_when_transcription_fails(self, qapp, tmp_path):
        backend = _Backend(error=RuntimeError("model exploded"))
        controller = _controller(qapp, backend, tmp_path)
        audio = _wav(tmp_path)
        errors: list[str] = []
        controller.error.connect(errors.append)

        controller._transcribe_file(str(audio))

        assert errors == ["model exploded"]
        assert not audio.exists()

    def test_empty_transcript_still_cleans_up(self, qapp, tmp_path):
        backend = _Backend(text="")
        controller = _controller(qapp, backend, tmp_path)
        audio = _wav(tmp_path)

        controller._transcribe_file(str(audio))

        assert not audio.exists()
