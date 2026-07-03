# llm_thalamus

**llm_thalamus** is a rich **Qt desktop GUI for the [pi coding agent](https://pi.dev/)**.

If you're already running local LLMs on capable hardware and using pi daily, llm_thalamus gives you a nicer environment to work in:

- **Multimedia interfaces** — voice recording (STT / Direct mode), image generation (SDXL / SD 1.5), text-to-speech (coqui-tts), inline image and audio display in chat. Media are passed through as `[file: /path]` references — vision-capable models can use their `read` tool to interpret them.
- **Rich message rendering** — LaTeX, code blocks with syntax highlighting, thinking blocks, tool call cards
- **Session management** — browse, resume, and fork pi sessions in a native tree view
- **Brain activity visualization** — animated brain widget during thinking
- **Native desktop feel** — no Electron, no Tauri, just PySide6 Qt
- **Totally local mode** — run fully offline with local models (in development, stubbed out)

llm_thalamus stays out of pi's way — it's a frontend, not a replacement. All the models, providers, skills, extensions, and tools you use in pi work the same way here.

## Prerequisites

**A fully configured pi coding agent installation is required.** llm_thalamus connects to `pi --mode rpc` as its backend — it does not ship its own LLM runtime.

This project targets users who already run local LLMs on capable hardware and work with pi daily. If that describes you, llm_thalamus layers on top of what you already have.

Install pi first:

```bash
yay -S pi-coding-agent-git
```

Configure it with at least one model, then proceed with llm-thalamus.

## Installation

**Install from AUR:**

```bash
yay -S llm-thalamus
```

That's it. All dependencies are handled by the package.

### Dev mode (no install)

```bash
git clone https://github.com/evertvorster/llm_thalamus.git
cd llm_thalamus

# Graphics for the brain widget are not in the repo. Grab them from a
# theme package, or generate your own — the widget expects:
#   resources/graphics/inactive.jpg <- General error
#   resources/graphics/thalamus.jpg <- Idle and ready
#   resources/graphics/llm.jpg      <- llm is working
# (the original image filenames still need renaming)

python -m src.llm_thalamus --dev
```

## Recommended: session persistence

llm_thalamus works with pi's built-in session system, but for virtually endless sessions with cross-session memory, install and configure:

- **[MemPalace](https://github.com/evertvorster/mempalace)** — long-term semantic memory for pi. Stores past decisions, preferences, project facts, and session context in a retrievable vector store. Pi picks it up automatically as an MCP tool.
- **Observational memory** — pi's built-in passive memory feature (enabled in `~/.pi/agent/settings.json` under `observational-memory`). Automatically captures observations from the conversation and reflects on them, keeping sessions grounded in past context without manual summarization.

With both enabled, sessions can effectively run indefinitely — pi keeps its own context window manageable through compaction while MemPalace preserves durable knowledge.

## Optional: voice and media features

llm_thalamus works as a plain chat GUI with just pi. The following features have additional dependencies.

### Speech-to-Text (voice recording → transcription)

Requires `python-faster-whisper` (available on AUR). Models download on first use — select one in Settings → Speech-to-Text.

### Direct voice mode (voice → audio-capable model)

Sends recorded audio directly to models that support audio input (e.g., Gemma 4). **Requires a patched pi** that passes audio through the RPC protocol, or pi upstream to add audio support in the RPC (`--mode rpc`).

**Current status:** Evert maintains a local `pi-coding-agent-voice-git` package from the `audio-rpc` branch. Upstream pi issue [#6118](https://github.com/earendil-works/pi/issues/6118) tracks adding audio to the RPC protocol.

### Image generation (SDXL / SD 1.5)

This is the trickiest optional dependency — getting a working torch + CUDA + diffusers environment can be version-sensitive.

**Dependencies:**

```
torch (with CUDA support)
diffusers
transformers
tokenizers
```

```bash
sudo pacman -S python-torch python-torch-cuda python-diffusers python-transformers python-tokenizers python-huggingface-hub
```

Then download the models:

```bash
# SDXL base (~7 GB)
hf download stabilityai/stable-diffusion-xl-base-1.0 --local-dir ~/models/sdxl-base

# SD 1.5 base (~2 GB)
hf download runwayml/stable-diffusion-v1-5 --local-dir ~/models/sd15
```

**Note on tokenizers compatibility:** These scripts apply a monkey-patch for `RobertaProcessing` API changes in newer `tokenizers` versions. If you encounter import errors, this is the likely cause.

**Configure paths** in Settings → Tool Extensions, then the `gen_image_sdxl` and `gen_image_sd15` tools will be available to any pi model.

### Text-to-Speech (coqui-tts)

Requires a coqui-tts virtual environment at `/opt/coqui-tts/venv/` with `TTS` installed, plus `pw-play` (pipewire) and `sox` for audio playback. Two pi extension tools (`tts-direct`, `tts-clone`) handle Tacotron2-DDC and XTTS v2 voice cloning. Configure model and paths in Settings → Tool Extensions.

## How it works

llm_thalamus spawns `pi --mode rpc` as a subprocess and communicates via JSON-RPC over stdin/stdout. The RPC protocol emits structured events (message turns, thinking blocks, tool calls, extension UI requests) that the Qt UI renders natively.

```
llm_thalamus (Qt GUI)  ←→  pi --mode rpc  ←→  LLM (via pi's provider layer)
```

The pi RPC bridge (`PiRPCBridge`) handles:
- Spawning and restarting pi
- Parsing RPC events into Qt signals
- Session management (new, switch, resume, delete)
- Sending user messages, images, and audio
- Handling model modality awareness (vision, audio)

No LangGraph, no MCP client, no embedded runtime — pi is the complete backend.

## Configuration

Settings are managed through the **Settings dialog** (4 tabs):

| Tab | What it controls |
|-----|-----------------|
| **Display** | Theme, auto-collapse thresholds for agent work, thinking, and tools |
| **pi Backend** | Default provider/model, thinking level, project trust, compaction, retry |
| **Speech-to-Text** | STT model management (download/delete), recording mode, voice mode, task, language |
| **Tool Extensions** | Paths for SDXL/SD 1.5 models, image output directory, TTS model/voice sample/output directory |

Settings are persisted to `~/.pi/agent/settings.json` (pi's config) and `QSettings` (llm-thalamus display settings).

## Source layout

```
src/
  llm_thalamus.py            Entry point
  controller/
    pi_bridge.py             PiRPCBridge — RPC subprocess + signal dispatch
    stt.py                   STT backend abstraction (faster-whisper)
  ui/
    main_window.py           Main window
    chat_renderer.py         Rich message rendering (HTML + JS)
    settings_dialog.py       Settings dialog (4 tabs)
    voice_controller.py      Microphone capture + STT/Direct mode
    widgets.py               ChatInput, BrainWidget, AttachmentBar
    model_dialog.py          Model picker
    session_dialog.py        Session browser
    command_palette.py       /-command palette
    attachment_bar.py        Drag-drop file attachment sidebar
    theme.py                 Shared theme constants
tests/
    test_chat_renderer.py    Pure-function rendering tests
    test_main_window.py      Qt offscreen window construction + wiring tests
    test_pi_bridge.py        RPC event parsing tests
    test_settings_dialog.py  Settings dialog widget defaults + persistence tests
```

## pi extensions

llm_thalamus ships pi custom tool extensions for media generation (installed to `~/.pi/agent/extensions/`):

| Tool | Extension | What it does |
|------|-----------|-------------|
| `gen_image_sdxl` | `image-gen/` | SDXL 1024×1024 image generation |
| `gen_image_sd15` | `image-gen/` | SD 1.5 512×512 image generation |
| `tts-direct` | `tts-direct/` | Tacotron2-DDC TTS |
| `tts-clone` | `tts-clone/` | XTTS v2 voice-cloned TTS |

These are standard pi extensions — any pi model can call them. Paths and model selection are configurable via Settings → Tool Extensions.

## Reference docs

| Document | What it covers |
|----------|---------------|
| [`docs/pi-rpc-integration.md`](docs/pi-rpc-integration.md) | Architecture, CLI flags, path resolution, dev/installed modes |
| [`docs/rpc-signal-mapping.md`](docs/rpc-signal-mapping.md) | Full RPC signal mapping, session management, command registry |
| [`docs/stt-integration-plan.md`](docs/stt-integration-plan.md) | Speech-to-Text implementation details |
| [`docs/renderer-spec.md`](docs/renderer-spec.md) | Chat renderer specification |

## License

See `LICENSE.md`.
