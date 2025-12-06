# LLM‑Thalamus Integrated Local Architecture  
*A consolidated design document for the controller + UI stack*

---

## 1. Purpose

LLM‑Thalamus is a **local cognitive controller** that wraps a local LLM (Ollama Qwen 2.5 7B) with:

- A structured 3‑phase reasoning loop (Answer → Reflect → Retrieve)
- A persistent long‑term memory system (OpenMemory)
- A short‑term episodic memory window (last 10 messages)
- A PySide6 desktop UI with Markdown/MathJax rendering
- Fully local execution; no server required

This document describes the architecture, subsystem responsibilities, lifecycle of a request, and how the UI and engine communicate.

It is the “source of truth” for future refactoring, debugging, and expansion.

---

## 2. Architecture Summary

### Components

```
+----------------------+
|  PySide6 UI          |
| - WebEngine view     |
| - Input box          |
| - Worker thread      |
+----------^-----------+
           |
           | Signals / slots
           v
+----------------------+       +----------------------+
|  ThalamusEngine      | <---- |  OpenMemory          |
| - LLM interface      |       | - Vector DB (SQLite) |
| - Memory pipeline    |       | - Embedding (Ollama) |
| - Prompt templates   |       +----------------------+
| - Chat history       |
+----------^-----------+
           |
           | HTTP
           v
+----------------------+
|   Ollama Runtime     |
|   Qwen2.5‑7B +       |
|   nomic‑embed-text   |
+----------------------+
```

There is *no server layer*; the UI directly instantiates and calls `ThalamusEngine`.

---

## 3. ThalamusEngine Responsibilities

### 3.1 Core duties

The engine is a **pure Python module** that exposes:

```python
run_turn(text) -> assistant_reply
reset_session()
simple_memory_query(...)
ingest_text(...)
```

It performs:

1. **Context building**
   - Recent memory retrieval from OpenMemory
   - Recent episodic dialog (last 10 messages)

2. **Three‑phase LLM workflow**
   - AnswerCall → produce final reply  
   - ReflectCall → extract structured memories, write to OM  
   - RetrieveCall → update retrieval plan for next turn

3. **Storage & continuity**
   - Chat history saved to JSON
   - Memory saved to OpenMemory
   - Retrieval plan saved to disk

4. **LLM interface**
   - Uses Ollama’s `/api/generate` and `/api/embed`

5. **Debug logging**
   - Controlled via config

---

## 4. Prompt Templates

The engine loads:

```
config/AnswerCall.txt
config/ReflectCall.txt
config/RetrieveCall.txt
```

Values inserted:

- `{{context_memories}}` → OpenMemory + recent dialog  
- `{{user_message}}`  
- `{{assistant_answer}}`  
- `{{conversation_history}}` (short one‑turn mini context)

Templates remain *engine‑agnostic* so UI or tools can reuse them.

---

## 5. Memory System

### 5.1 Long‑term memory — OpenMemory

Stored as structured objects with fields:

```
type: fact | persona | rule | concept | turn? (future)
topic: free‑form categorization
fact_key: optional unique key for evolution
importance: ranking for retrieval selection
metadata: arbitrary dict
```

Embedding provider:

```
provider: "ollama"
model: "nomic-embed-text"
ollama_url: http://localhost:11434
```

### 5.2 Short‑term memory — Ephemeral dialog

Not stored in OpenMemory.

Engine maintains full `chat_history.json`, but exposes **only last 10 messages** to LLM.

This prevents contamination of long‑term memory while preserving flow.

---

## 6. Retrieval Plan (Dynamic Memory Selection)

The retrieval plan is a JSON file:

```
config/retrieval_plan.json
```

Updated every turn by RetrieveCall and loaded next turn.

Structure:

```json
{
  "retrieval_instructions": [
    {
      "topic": "...",
      "types": ["fact", "persona"],
      "query": "...",
      "limit": 10
    }
  ]
}
```

The plan tells the engine which memory vectors to query.

---

## 7. UI–Engine Integration

### 7.1 Communication Model

The UI never blocks; it sends requests via a worker thread:

```
User → UI → WorkerThread.run_turn() → Engine → LLM/OM
                                   → UI callback → WebEngine append
```

### 7.2 Rendering Pipeline

- Markdown rendered via `marked.js`
- Code blocks highlighted via `highlight.js`
- Math rendered via MathJax
- Backslash‑based TeX preserved using `.split().join()` pre‑processor step

### 7.3 Message delivery

Engine emits the **final assistant reply** only (not reflection artifacts).

UI injects messages via:

```js
window.appendMessage(role, html_content)
```

where content has already been Markdown‑compiled.

---

## 8. Config System

Single JSON file:

```
config/config.json
```

Contains:

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:7b"
  },
  "openmemory": {
    "db_path": "data/memory.db",
    "tier": "deep",
    "embedding_provider": "ollama",
    "embedding_model": "nomic-embed-text",
    "ollama_url": "http://localhost:11434"
  },
  "runtime": {
    "log_path": "thalamus-debug.log"
  },
  "prompts": {
    "answer_call": "config/AnswerCall.txt",
    "reflect_call": "config/ReflectCall.txt",
    "retrieve_call": "config/RetrieveCall.txt"
  }
}
```

UI will eventually expose a config editor.

---

## 9. Turn Lifecycle (Step‑By‑Step)

### **Input**
User enters text in UI → worker thread receives it.

### **Step 1 — Context assembly**
Engine builds:

- `context_memories` from OM retrieval plan  
- `recent_history` from last 10 dialog messages  
- Combined `full_context_text`

### **Step 2 — AnswerCall**
Engine fills AnswerCall template:

```
context = full_context_text
user_message = raw user input
```

Sends to Ollama → receives assistant final reply.

### **Step 3 — ReflectCall**
Engine fills ReflectCall template with:

- context
- user message
- assistant answer

Ollama returns structured memory JSON → engine stores valid memories.

### **Step 4 — RetrieveCall**
Model returns retrieval instructions → engine stores plan → next turn uses it.

### **Step 5 — Chat history**
Both user + assistant messages appended to disk.

### **Step 6 — Return to UI**
Final assistant reply is sent back to UI for rendering.

---

## 10. Extensibility Roadmap

### Soon:
- History viewer & cleaner in UI
- Config editor dialog
- Hot‑reloading prompt templates
- Toggle memory categories (identity, preferences, tasks)

### Later:
- Episodic “turn memory” stored in OpenMemory with controlled importance
- Task‑mode memory buckets (e.g. “math session”, “coding session”)
- Time‑weighted forgetting
- Built‑in RAG support for user files

---

## 11. Safety + Stability Rules

- Only ReflectCall may create or modify memories.
- AnswerCall never writes state.
- RetrievalCall must not modify non‑retrieval system files.
- If ReflectCall returns invalid JSON, no memory writes occur.
- Retrieval plan must remain well‑formed; fallback to safe default if corrupted.
- UI sandboxing: JS must never issue network requests or file writes.

---

## 12. Summary

LLM‑Thalamus + UI is a fully local cognitive system providing:

- LLM reasoning loop  
- Memory persistence  
- Intelligent context retrieval  
- Display‑safe rendering  
- Zero‑server deployment  

This document defines a stable foundation for future features and refactoring.
