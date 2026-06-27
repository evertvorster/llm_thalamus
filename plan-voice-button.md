# Plan: Single Voice button + direct mode

## Current state
- Two mic buttons in input row: 🎤 STT and 🎤 Audio
- 🎤 STT: record → whisper → insert text in input
- 🎤 Audio: record → insert `[file: ...]` in input

## Changes

### Layout
Remove both mic buttons from the input row. Add one **Voice** button to the buttons column (above Send):

```
[ChatInput] [🧠] [buttons column: Voice, Send, Follow up, Session, Settings, Quit]
```

### Config: `stt/voice_mode`

New QSettings key in Speech-to-Text tab:

| Mode | Behavior on release |
|------|-------------------|
| **STT** | Record → whisper → insert transcribed text into input (current STT behavior) |
| **Direct** | Record → save to attachments dir → send `[file: path]` as a message immediately |

Both modes support push-to-talk (hold/release) and dialog (click start/click stop).

### Flow

**STT mode** (unchanged from today's 🎤 STT):
1. Press/hold → record
2. Release → whisper → text appears at cursor in input
3. User edits text, clicks Send

**Direct mode** (new):
1. Press/hold → record
2. Release → save WAV to `~/.pi/agent/sessions/attachments/`
3. Send `[file: /path/to/recording.wav]` as a message automatically
   - Same as clicking Send with the file reference
   - Appears in chat as `[file: recording-....wav]` (short name)
   - Model receives full path

### Settings dialog
Add a `Voice Mode` QComboBox with "STT" and "Direct" options in the Speech-to-Text tab, after the Recording mode row.

### Implementation order

1. Add `stt/voice_mode` setting (STT/Direct)
2. Replace two mic buttons with one Voice button in buttons column
3. Wire Voice button: read mode setting, route to STT or Direct path
4. Wire settings dialog with Voice Mode combo
5. Clean up old mic button code
