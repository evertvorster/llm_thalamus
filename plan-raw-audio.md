# Plan: Raw audio recording for voice-capable models

## What changes

Currently the mic button records audio → transcribes via faster-whisper → inserts text.
For voice-capable models, we want a **second path**: record audio → save file → insert `[file: recording.wav]` reference.

## UI

**Two mic buttons** (as planned in the STT doc, now unblocked):

| Button | Label | Behavior | When visible |
|--------|-------|----------|-------------|
| 🎤 Audio | Raw audio record | Hold → record → release → `[file: ...wav]` inserted | When current model supports audio |
| 🎤 STT | Transcribe | Hold → record → release → transcribe → text inserted | When faster-whisper is installed |

Visibility:
- **Audio-only model**: show 🎤 Audio, hide 🎤 STT
- **Text-only model with STT**: show 🎤 STT, hide 🎤 Audio
- **Both**: show both
- **Neither**: hide both (same as today)

Model capability determined by pi's `get_state` response (model config may include whether it accepts audio).

## Recording file storage

Move from `/tmp/` to the attachment directory:
```
~/.pi/agent/sessions/attachments/recording-{timestamp}.wav
```
This keeps recordings accessible to the model throughout the session.

## File reference

After recording, the mic button inserts `[file: /path/to/recording.wav]` at the cursor — same placeholder system as drag-and-drop. The model receives the full path on send and can read the WAV file directly (or run whisper on it via tools).

## Implementation steps

1. Create the attachment directory (`~/.pi/agent/sessions/attachments/`)
2. Add a second mic button ("🎤 Audio") alongside the existing "🎤 STT" button
3. Wire recording to save to the attachment directory instead of /tmp
4. On release (raw audio mode): insert `[file: path]` instead of transcribing
5. Show/hide buttons based on model capability (from `get_state`)
6. Clean up old recordings (optional — could leave for model access)

## Future

- Dialog mode for raw audio recording (start/stop with a single click)
- Configurable recording format (WAV, FLAC, OGG)
