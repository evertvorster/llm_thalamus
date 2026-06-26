"""STT (Speech-to-Text) backend abstraction.

Provides a backend-agnostic interface for speech recognition.
Currently only ``faster-whisper`` is implemented; other backends can
be added by implementing ``SttBackend`` and registering via
``register_backend()``.

Usage::

    from controller.stt import available_backends, get_backend

    backends = available_backends()
    stt = get_backend("faster-whisper")
    if stt is not None:
        text = stt.transcribe("/tmp/recording.wav", model="base")
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol


# ── Backend interface ───────────────────────────────────────────────


class SttBackend:
    """Interface every STT backend must implement.

    All methods are allowed to raise ``SttBackendError`` (or a subclass).
    """

    @property
    def name(self) -> str:
        """Human-readable backend name (e.g. ``"faster-whisper"``)."""
        ...

    def available_models(self) -> list[str]:
        """Return the list of model identifiers this backend knows about."""
        ...

    def is_model_downloaded(self, model: str) -> bool:
        """Return True if *model* is already cached locally."""
        ...

    def download_model(self, model: str) -> None:
        """Download *model* to the local cache.

        May block for a significant time (minutes for large models).
        Callers should run this on a background thread.
        """
        ...

    def delete_model(self, model: str) -> None:
        """Remove a previously downloaded model from the cache."""
        ...

    def cache_info(self) -> dict:
        """Return dict with cache statistics::

            {
                "location": "/home/user/.cache/huggingface/hub",
                "size_bytes": 123456789,
                "models": [
                    {"name": "base", "size_bytes": 300000000, "downloaded": True},
                    ...
                ],
            }
        """
        ...

    def transcribe(self, audio_path: str, model: str = "base") -> str:
        """Transcribe *audio_path* (a WAV file) using *model*.

        Returns the transcribed text as a single string.

        Raises:
            ModelNotDownloaded: if *model* is not cached.
            TranscriptionError: if the STT engine fails.
        """
        ...


# ── Errors ──────────────────────────────────────────────────────────


class SttBackendError(Exception):
    """Base exception for all STT-backend errors."""


class BackendUnavailable(SttBackendError):
    """The requested backend is not installed on this system."""


class ModelNotDownloaded(SttBackendError):
    """The model has not been downloaded yet."""


class TranscriptionError(SttBackendError):
    """The transcription engine returned an error."""


# ── Backend registry ────────────────────────────────────────────────

_BACKENDS: dict[str, type[SttBackend]] = {}


def register_backend(name: str, cls: type[SttBackend]) -> None:
    """Register a backend class under *name*.

    Called at module import time by each backend implementation.
    """
    _BACKENDS[name] = cls


def available_backends() -> list[str]:
    """Return names of all registered backends."""
    return list(_BACKENDS.keys())


def get_backend(name: str) -> SttBackend | None:
    """Instantiate and return the backend registered as *name*.

    Returns ``None`` if the backend is registered but its dependencies
    are not installed on this system.
    """
    cls = _BACKENDS.get(name)
    if cls is None:
        return None
    try:
        return cls()
    except BackendUnavailable:
        return None


# ═════════════════════════════════════════════════════════════════════
# faster-whisper backend
# ═════════════════════════════════════════════════════════════════════


class FasterWhisperBackend(SttBackend):
    """STT backend wrapping ``faster_whisper``.

    Raises ``BackendUnavailable`` if ``faster_whisper`` is not installed.
    """

    _MODEL_PREFIX = "Systran/faster-whisper-"
    _HF_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"
    _INSTANCE: "FasterWhisperBackend | None" = None  # singleton
    _MODEL_INSTANCE: object | None = None             # cached WhisperModel
    _CURRENT_MODEL: str | None = None                 # which model is loaded

    def __init__(self) -> None:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            raise BackendUnavailable(
                "faster-whisper is not installed. "
                "Install python-faster-whisper and try again."
            ) from None
        self._fw = faster_whisper
        # Store the module-level reference so we don't re-import every call.

    @property
    def name(self) -> str:
        return "faster-whisper"

    # ── model enumeration ──────────────────────────────────────────

    def available_models(self) -> list[str]:
        return list(self._fw.available_models())

    # ── download management ────────────────────────────────────────

    def is_model_downloaded(self, model: str) -> bool:
        return self._model_dir(model).exists()

    def download_model(self, model: str) -> None:
        self._fw.download_model(model)

    def delete_model(self, model: str) -> None:
        path = self._model_dir(model)
        if path.exists():
            shutil.rmtree(path)
            # If this was the currently-loaded model, clear the singleton.
            if self._CURRENT_MODEL == model:
                self.__class__._MODEL_INSTANCE = None
                self.__class__._CURRENT_MODEL = None

    def cache_info(self) -> dict:
        # Gather info from the huggingface hub cache.
        models_info: list[dict] = []
        total_size = 0

        for model_name in self.available_models():
            mdir = self._model_dir(model_name)
            downloaded = mdir.exists()
            size = 0
            if downloaded:
                size = self._dir_size(mdir)
                total_size += size
            models_info.append({
                "name": model_name,
                "size_bytes": size,
                "size_human": _fmt_bytes(size),
                "downloaded": downloaded,
            })

        return {
            "location": str(self._HF_CACHE_DIR),
            "size_bytes": total_size,
            "size_human": _fmt_bytes(total_size),
            "models": models_info,
        }

    # ── transcription ──────────────────────────────────────────────

    def transcribe(self, audio_path: str, model: str = "base") -> str:
        if not os.path.isfile(audio_path):
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        # Load the model (cached singleton — re-created only on size change).
        engine = self._get_or_create_model(model)

        segments, info = engine.transcribe(audio_path)
        text_parts: list[str] = []
        for seg in segments:
            text_parts.append(seg.text)

        return "".join(text_parts).strip()

    # ── internals ──────────────────────────────────────────────────

    def _get_or_create_model(self, model_name: str) -> object:
        """Return a cached ``WhisperModel``, creating one if needed.

        If *model_name* differs from the currently cached model,
        the old instance is discarded and a new one is created.
        """
        cls = self.__class__

        # Model change → discard old.
        if cls._CURRENT_MODEL is not None and cls._CURRENT_MODEL != model_name:
            cls._MODEL_INSTANCE = None
            cls._CURRENT_MODEL = None

        if cls._MODEL_INSTANCE is None:
            if not self.is_model_downloaded(model_name):
                raise ModelNotDownloaded(
                    f"Model '{model_name}' is not downloaded. "
                    "Call download_model() first."
                )
            # Loading the model is slow (several seconds for "base").
            # We use device="cpu" and compute_type="int8" for broad
            # compatibility. Users with GPU support can configure
            # a different compute_type via settings later.
            cls._MODEL_INSTANCE = self._fw.WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
            )
            cls._CURRENT_MODEL = model_name

        return cls._MODEL_INSTANCE

    def _model_dir(self, model_name: str) -> Path:
        """Return the HuggingFace cache directory for *model_name*.

        Faster-whisper downloads to a snapshot dir inside the HF hub cache:
        ``models--Systran--faster-whisper-{model_name}/snapshots/<hash>/``
        """
        repo_dir_name = f"models--Systran--faster-whisper-{model_name}"
        return self._HF_CACHE_DIR / repo_dir_name

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
        return total


# ── auto-register ───────────────────────────────────────────────────

register_backend("faster-whisper", FasterWhisperBackend)


# ── helpers ─────────────────────────────────────────────────────────


_MODEL_SIZES: dict[str, str] = {
    "tiny": "~150 MB",
    "tiny.en": "~150 MB",
    "base": "~300 MB",
    "base.en": "~300 MB",
    "small": "~1.5 GB",
    "small.en": "~1.5 GB",
    "medium": "~3 GB",
    "medium.en": "~3 GB",
    "large": "~6 GB",
    "large-v1": "~6 GB",
    "large-v2": "~6 GB",
    "large-v3": "~6 GB",
    "large-v3-turbo": "~3 GB",
    "turbo": "~3 GB",
    "distil-large-v2": "~3 GB",
    "distil-large-v3": "~3 GB",
    "distil-large-v3.5": "~3 GB",
    "distil-medium.en": "~1.5 GB",
    "distil-small.en": "~700 MB",
}


def model_size_human(name: str) -> str:
    """Return a human-readable size hint for a model name."""
    return _MODEL_SIZES.get(name, "")


def _fmt_bytes(n: int) -> str:
    """Format bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
