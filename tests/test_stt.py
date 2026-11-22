"""Tests for the STT backend's file-touching paths.

The model cache is deleted with ``rmtree``, so the name that builds that path is
the one thing here worth pinning: a name that is not a plain path component must
be refused rather than joined into a path outside the cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _backend(tmp_cache: Path):
    """A backend whose cache lives in a temp dir, without importing faster-whisper."""
    from controller.stt import FasterWhisperBackend

    backend = FasterWhisperBackend.__new__(FasterWhisperBackend)
    type(backend)._HF_CACHE_DIR = tmp_cache      # class attribute, overridden here
    return backend


class TestModelDir:
    def test_plain_name_stays_in_the_cache(self, tmp_path):
        backend = _backend(tmp_path)
        assert backend._model_dir("base") == (
            tmp_path / "models--Systran--faster-whisper-base"
        )

    @pytest.mark.parametrize("name", ["../escape", "a/b", "..", "", "x\0y", "  "])
    def test_bad_name_is_refused(self, tmp_path, name):
        backend = _backend(tmp_path)
        with pytest.raises(ValueError):
            backend._model_dir(name)

    def test_bad_name_cannot_delete_anything(self, tmp_path):
        """The guard runs before rmtree, so an escaping name touches nothing."""
        backend = _backend(tmp_path)
        victim = tmp_path.parent / "victim"
        victim.mkdir()

        with pytest.raises(ValueError):
            backend.delete_model("../victim")

        assert victim.exists()
        victim.rmdir()
