# Contributing to LLM Thalamus

Thank you for your interest in contributing!

LLM Thalamus is a fully local AI framework whose goals are:
- Privacy
- Extensibility
- Stability
- User control
- High‑context memory

This document describes how to contribute code, report bugs, propose features, and help shape the project.

---

# 🧱 Project Principles

### 1. Local‑First
Everything must run offline:
- LLM (Ollama)
- Memory embeddings (OpenMemory)
- UI (PySide6)
- Storage (SQLite)

### 2. Modular
Each component should be replaceable or extendable:
- Memory tools
- Ingest modules
- Retrieval paths
- UI panels
- Tooling

### 3. Predictable Behavior
The assistant should behave consistently and transparently.  
Avoid “black‑box” tricks or layers that obscure logic flow.

---

# 🛠 Development Setup

Clone the repository:

```bash
git clone https://github.com/evertvorster/llm-thalamus
cd llm-thalamus
```

Install development dependencies:

```bash
pacman -S pyside6 qt6-webengine katex python-markdown-it-py python-requests ollama
yay -S python-openmemory-py
```

Run the UI in development mode:

```bash
python llm_thalamus/llm_thalamus_ui.py
```

The `paths.py` module ensures the program uses development paths automatically when run from the repo.

---

# 📦 Building & Installing

To test installation:

```bash
makepkg -si
```

To install manually:

```bash
sudo make install
```

Uninstall:

```bash
sudo make uninstall
```

---

# 🔧 Coding Guidelines

## Python Style
- Follow PEP8 where possible
- Prefer small, composable functions
- Avoid duplication—centralize logic
- Use descriptive variable names
- Keep UI code clean and modular

## Memory & Engine Rules
- Never bypass the memory engine’s ingestion hooks
- Retrieval should remain pluggable
- Avoid unpredictable or stateful side effects
- All knowledge must be storable and retrievable locally

---

# 🧪 Testing

Use `pytest`:

```bash
pytest -v
```

Tests live in:

```
tests/
```

If adding new memory or retrieval logic, include corresponding tests.

---

# 🐛 Bug Reports

When reporting a bug, include:

1. Steps to reproduce  
2. What you expected  
3. What happened instead  
4. Logs from:

```
~/.local/share/llm-thalamus/log/
```

Screenshots of UI issues are extremely helpful.

---

# 💡 Feature Requests

Feature requests should include:

- A clear motivation
- Expected behavior
- UI implications (if any)
- How it integrates with thalamus or memory

If the feature touches multiple layers (UI + engine + memory), submit a design proposal first.

---

# 🔐 Security

All contributions must preserve the project’s privacy guarantees:

- No external network calls except to Ollama localhost
- No telemetry
- No cloud API usage
- No silent logging of sensitive data

---

# 🙌 Thanks

Your contributions help shape LLM Thalamus into a powerful, private, local AI framework.
We appreciate all PRs, bug reports, and ideas!

