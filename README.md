# LLM Thalamus
*A local-first AI controller, memory engine, and PySide6 user interface for personal assistants.*

LLM Thalamus is a modular, extensible framework for running a local AI “brain” on your own machine.
It orchestrates an LLM (Ollama), a memory system (OpenMemory), and a Qt6/PySide6 desktop UI.
It is fully local — **no cloud APIs, no tracking, no dependencies on proprietary services.**

This project was designed for people who want a **persistent, privacy‑respecting, high‑context AI assistant** that lives on their computer and evolves over time.

---

## ✨ Features

### 🧠 Persistent Memory (OpenMemory)
- Semantic memory (knowledge, facts, structured data)
- Episodic memory (chat logs, user sessions)
- High‑quality retrieval via nomic‑embed‑text embeddings
- Local SQLite storage — no remote servers
- Automatic ingestion and retrieval flow integrated into the thalamus engine

### 💬 PySide6 Desktop UI
- Markdown renderer
- KaTeX math rendering (system katex)
- Syntax‑highlighted code blocks
- Multi‑panel interface for Chats, Documents, Spaces, and Config
- Real‑time engine status indicators
- Works in both development and installed mode

### 🔌 Thalamus Engine (Controller)
- Handles conversation flow
- Routes messages to memory ingestion / retrieval tools
- Reflection passes for improved memory formation
- Tool invocation and metadata extraction
- Manages the assistant’s reasoning loop

### 🔒 Fully Local Execution
- Uses **Ollama** to run LLM models offline  
- Uses **OpenMemory** to store embeddings and vectors offline  
- No telemetry, no cloud calls, completely air‑gapped capable

---

## 🚀 Installation

### System Dependencies
```
python
pyside6
qt6-webengine
python-markdown-it-py
python-requests
python-openmemory-py
katex
ollama
highlightjs
```

Arch users:
```bash
pacman -S pyside6 qt6-webengine python-markdown-it-py python-requests katex ollama
yay -S python-openmemory-py
```
***Note***
Default ollama runs on CPU, for faster responses, install one of the other
ollama variants in the repo for GPU or NPU acceleration.

---

## 1. Required LLM Models (Ollama)

### Qwen2.5‑Instruct (7B)
Main reasoning model.

Install:
```bash
ollama pull qwen2.5:7b
```

> We **develop and test** with the 7B variant.  
> Larger models work, but **YMMV** in memory behavior or inference timing.
> Testing system has 16Gb Dedicated GPU. For systems with less resources:
  - qwen2.5:3b
  - qwen2.5:1.5b
  - qwen2.5:0.5b
The "b" denotes billions of parameters, less is smaller and faster, but
also less capable.
---

### nomic‑embed‑text
Embedding model for OpenMemory.

Install:
```bash
ollama pull nomic-embed-text
```

Used for:
- Document embeddings  
- Memory embeddings  
- Semantic search  
- Retrieval augmentation  

---

## 2. Installing LLM Thalamus

### AUR
```bash
yay -S llm-thalamus
```

### From source
```bash
makepkg -si
```
or:
```bash
sudo make install
```

Installs:
- `/usr/lib/llm_thalamus/` (Python modules)
- `/usr/bin/llm-thalamus*` (executables)
- `/etc/llm-thalamus/config.json` (template config)
- `/usr/share/llm-thalamus/graphics/` (icons & brain images)
- `/usr/share/applications/llm_thalamus.desktop` (launcher)

User config and databases appear under:

```
~/.config/llm-thalamus/
~/.local/share/llm-thalamus/data/
```

---

## 🧭 Running the UI

Launch:
```
llm-thalamus-ui
```

Or click **LLM Thalamus** in your desktop’s application launcher.

---

## 🗂 Project Structure

```
llm_thalamus/
   llm_thalamus.py               – Engine / thalamus controller
   llm_thalamus_ui.py            – PySide6 user interface
   memory_storage.py             – Writing semantic & episodic memories
   memory_retrieval.py           – Querying memory stores
   memory_ingest.py              – Ingestion of files and text chunks
   memory_retrieve_documents.py  – Document search & retrieval
   spaces_manager.py             – Namespace and DB mapping
   retrieve_ingested_file.py     – Document fetch helper
   tool_registry.py              – Tool registration
   paths.py                      – Development/install path manager
   graphics/                     – Icons + glowing brain images
   config/config.json            – Default config template
```

---

## 🔒 Privacy Advantages

- Local inference  
- Local embeddings  
- Local memory  
- No telemetry  
- No analytics  
- No cloud dependencies  

Perfect for:
- Developers  
- Researchers  
- Writers  
- Privacy‑focused users  
- Air‑gapped environments  

---

## 💡 Vision

LLM Thalamus aims to become a complete, self‑contained personal AI ecosystem:
- Persistent, growing memory  
- Local LLM reasoning  
- Document knowledge  
- Multi‑tool orchestration  
- Optional voice modules  
- Image models  
- Extensible UI

All while remaining fully offline and user‑controlled.

---

## 📣 Contributions
See **CONTRIBUTING.md** for guidelines on contributing, bug reporting, and feature proposals.
If you clone the repo, you should be able to run it in the thalamus subdirectory with:
```
python llm_thalamus_ui.py
```
This will not affect the installed version, and use its own config and databases.

Pull requests welcome!
