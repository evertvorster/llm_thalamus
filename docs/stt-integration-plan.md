# STT Integration — Implementation Plan

**Status:** Implemented 2026-06-26.

See the [Obsidian vault plan](https://github.com/evertvorster/llm-thalamus) for the full updated checklist.

## Overview

Add speech-to-text to llm-thalamus using `faster-whisper` as the first backend.
Record audio from the microphone → transcribe → paste text into the chat input box.

Two paths depending on model support:
- **STT (text-only):** Record → transcribe via faster-whisper → transcribed text in input box
- **Raw audio (voice-capable model):** Record → send audio file path via RPC (blocked on pi RPC support, not implemented yet)

---

## What was built

### 1. `src/controller/stt.py` — Backend wrapper

- `SttBackend` abstract interface: `transcribe()`, `available_models()`, `download_model()`, `delete_model()`, `cache_info()`
- `FasterWhisperBackend` implementation wrapping `faster_whisper` library
- `model_size_human()` helper for download size hints
- Backend registry via `available_backends()` / `get_backend()` factory
- Singleton model instance — `WhisperModel` cached and re-created only on model size change
- Exceptions: `BackendUnavailable`, `ModelNotDownloaded`, `TranscriptionError`

### 2. Recording — `QAudioSource` → WAV

- Uses `QAudioSource` (not `QMediaRecorder`) to capture raw 16-bit PCM at 16kHz mono
- Data accumulates in a `QBuffer` during recording
- On release: writes a proper WAV file via Python's `wave` module
- Reason: Qt's FFmpeg-backed `QMediaRecorder` doesn't flush WAV headers properly on this system
- Temp files: `/tmp/llm-thalamus-recording-{timestamp}.wav`, cleaned up after transcription

### 3. Mic button — push-to-talk

- 🎤 STT button in the input area (between chat input and brain widget)
- Hold to record (button turns red with ■), release to transcribe
- Mic button text cycles: 🎤 STT → 🎤 ■ (recording) → 🎤 … (transcribing) → 🎤 STT (done)
- Recorder errors shown in `QMessageBox.warning()`

### 4. Settings tab

- New "Speech-to-Text" tab in the settings dialog
- Backend status (✓ available / ✗ not installed)
- Model selector + Download/Delete buttons
- Cache info: location, total size, per-model download status
- Recording mode selector (Push-to-talk / Dialog — only push-to-talk wired)
- Settings persisted in QSettings (`stt/model`, `stt/recording_mode`)

### 5. Auto-download

- If the selected model isn't cached, pressing the mic button triggers auto-download
- Background thread with `QProgressDialog` (indeterminate)
- On completion: transcribes immediately
- On failure: shows error dialog

---

## 3. UI — Settings dialog

### New "Speech-to-Text" tab in settings

| Widget | Purpose |
|--------|---------|
| Backend selector | QComboBox listing available backends |
| Model selector | QComboBox populated from `backend.available_models()` |
| Download button | Downloads the selected model, shows progress |
| Delete button | Deletes the cached model |
| Cache info | QLabel showing cache dir + size + what's cached |
| Recording mode | QComboBox (push-to-talk / dialog) |
| Default mic | QComboBox listing available input devices |
| Test button | Record 3s, transcribe, show result in a message box |

### State reflects current backend

- Changing backend updates the model/cache widgets
- Models not yet downloaded are marked clearly (e.g. "(not downloaded)")
- If no backend available, entire tab is greyed out with a message

---

## 4. UI — Mic button(s) in ChatInput

- Add a `QPushButton` with mic icon next to the Send button
- On click: start/stop recording depending on mode
- STT result text is inserted at cursor position in the input box
- For push-to-talk: `mousePressEvent` starts recording, `mouseReleaseEvent` stops + transcribes

---

## 5. Configuration — QSettings

STT settings stored in QSettings under the `stt/` group:

```ini
stt/backend=faster-whisper
stt/model=base
stt/recording_mode=push-to-talk   # push-to-talk | dialog
stt/default_mic=                  # empty = system default
```

---

## Implementation order

1. **`src/controller/stt.py`** — Backend wrapper + faster-whisper backend
2. **STT settings tab** — Add to existing settings dialog in `main_window.py`
3. **Recording** — Mic button in ChatInput + audio capture
4. **Integration** — Wire mic → record → transcribe → input, connect settings

---

## Open questions

- Does PySide6 have Qt Multimedia available? (`pip list | grep PySide6` shows which Qt modules are bundled)
- What's the simplest WAV recording path? `QAudioSource` + manual WAV header, or `QMediaRecorder`?
- How long does `WhisperModel("base", device="cpu")` take to initialize? (loading the model is slow — should we keep a singleton?)
