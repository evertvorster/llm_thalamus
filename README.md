# llm-thalamus
A local, extensible computer-intelligence architecture with memory, tools, and a customizable UI.

## Overview
**llm-thalamus** is the core control system for a fully local, privacy-respecting “computer intelligence” — a reasoning engine that combines:
- a local LLM (via Ollama)
- short-term conversational memory
- long-term semantic memory (via OpenMemory)
- a dynamic tool-calling system
- a flexible working-phase reasoning loop
- a separate UI layer for interaction

The system runs entirely on your machine. No cloud. No tracking.

## Features
### Short-term Conversation Memory
Maintains a rolling window of messages for continuity across turns.

### Long-term Semantic Memory
Powered by OpenMemory, storing stable reflections that help the assistant adapt.

### Tools System
The assistant can request tools dynamically:
- memory retrieval
- future image generation
- file access
- system utilities

### Working Phase
Before answering, the LLM may:
- examine context
- request tools
- refine understanding

### UI Integration
The UI interacts with thalamus through an event-based interface:
- chat messages
- status updates
- control entries
- session lifecycle events

## Installation (Arch Linux)
Once published to AUR:
```
yay -S llm_thalamus
```

### Download required models:
```
llm_thalamus_download_models
```

## Repository Structure
```
llm_thalamus/
├── llm_thalamus.py
├── tool_registry.py
├── memory_retrieval.py
├── memory_storage.py
├── config/
│   ├── config.json
│   ├── prompt_answer.txt
│   ├── prompt_reflection.txt
│   └── prompt_retrieval_plan.txt
├── scripts/
│   └── llm_thalamus_download_models.sh
├── logs/        (ignored)
├── sessions/    (ignored)
└── data/        (ignored)
```

## Why “Computer Intelligence”?
This system is not a chatbot — it's a cognitive substrate capable of memory, reasoning, tool-use, and adaptation. A fully local personal intelligence.

## License
see LICENSE
