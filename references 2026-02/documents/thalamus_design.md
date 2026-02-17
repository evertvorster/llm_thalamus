
# llm-thalamus – Backend Controller Design Document

**File:** `llm_thalamus.py`  
**Version:** 2025-12-05  
**Project:** llm-thalamus  
**Purpose:** Orchestrate message flow between UI, memory system, LLM, and future modules.

---

# 1. Overview

Thalamus is the central controller of the llm-thalamus project:

- It orchestrates the assistant’s session loop.
- It delegates heavy tasks to external modules.
- It emits events consumed by the PySide6 UI.
- It loads all LLM prompts from external text files.
- It ensures a clean separation between:
  - UI  
  - Memory system  
  - LLM engine (Ollama)  
  - Future tools (STT/TTS, Stable Diffusion, CV modules)

Thalamus is intentionally **single-threaded** and designed to remain **compact**.

---

# 2. Responsibilities

## 2.1 Session Control

Each user message triggers a full session:

1. Emit `session_started`
2. Retrieve relevant memories
3. Build LLM prompt (system + payload)
4. Send answer call to LLM
5. Emit assistant reply directly to UI
6. Run reflection call (optional)
7. Store memory notes
8. Emit `session_ended`

## 2.2 Memory Integration

Thalamus uses OpenMemory via:

- `query_memories(query, user_id, k)`
- `store_semantic(content, tags, metadata, user_id)`

Memory retrieval returns a formatted text block for the LLM.

Reflection creates long‑term semantic notes.

## 2.3 LLM Integration (Ollama)

A lightweight client:

```
POST /api/chat { model, messages, stream: false }
```

Messages include the system prompt and wrapped payload.

Thalamus does *not* alter the LLM’s output.

## 2.4 Event Broadcasting

`ThalamusEvents` exposes:

- `on_chat_message(role, content)`
- `on_status_update(subsystem, status, detail)`
- `on_thalamus_control_entry(label, text)`
- `on_session_started()`
- `on_session_ended()`

The UI binds these callbacks.

---

# 3. Configuration

Loaded from:

```
config/config.json
```

Prompts are defined externally to reduce Python file size.

Example fields:

```json
"thalamus": {
    "project_name": "llm-thalamus",
    "default_user_id": "default",
    "llm_model": "qwen2.5:7b",
    "max_memory_results": 20,
    "enable_reflection": true
}
```

Logging and prompt file paths are also configurable.

---

# 4. Core Components

## 4.1 PromptManager

- Lazily loads prompt text files
- Caches them
- Falls back to default text
- Supports:
  - `answer`
  - `reflection`
  - `retrieval_plan` (future)

## 4.2 MemoryModule

Abstraction over OpenMemory.

Responsibilities:

- Retrieve semantic memories
- Store reflection results
- Filter irrelevant items (future)

## 4.3 OllamaClient

Minimal wrapper around Ollama API.

No streaming.

## 4.4 Thalamus Class

Coordinates all steps.

State:

- `last_user_message`
- `last_assistant_message`
- configuration + events + managers

Methods:

- `process_user_message`
- `_call_llm_answer`
- `_call_llm_reflection`
- `_debug_log`
- `_new_session_id`

---

# 5. Message Flow

### 5.1 Memory Retrieval

```
mem_block = query_memories(user_msg, k=20)
```

Returned as a formatted text block.

### 5.2 Answer Stage

```
system prompt + payload
→ LLM
→ Assistant reply
→ UI
```

### 5.3 Reflection Stage

```
system prompt (reflection)
+ “User message”
+ “Assistant reply”
→ LLM
→ Notes saved to memory
```

---

# 6. Error Handling

Thalamus:

- Never crashes the UI
- Emits error status events
- Logs full tracebacks
- Continues operating even if a module fails

---

# 7. Extensibility

New tools can be added by:

1. Adding new Thalamus events
2. Adding a module call inside Thalamus
3. Sending results back through event callbacks
4. Defining new config sections
5. Extending UI to show tool status

Thalamus remains the central router, not a processing engine.

---

# 8. Conclusion

Thalamus provides:

- A predictable control flow
- Seamless UI integration
- Robust session lifecycle
- Clean memory + LLM orchestration
- A foundation for expanding into a full local AI system

Its design is intentionally simple, modular, and maintainable.
