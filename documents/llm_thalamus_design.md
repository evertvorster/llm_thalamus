
# LLM‑Thalamus + Local UI Integration  
## Design Document (v1.0)

This document describes the architecture and data‑flow of the **LLM‑Thalamus** system integrated tightly with a **local Python/Qt UI**, running entirely offline.  
Its mission is to provide a consistent, memory‑aware conversational intelligence with stable identity, long‑term recall, and project continuity.

---

# 1. High‑Level Architecture

```
+-------------------------+
|       Local UI          |
|  (Python + Qt6/PySide6) |
+-----------+-------------+
            |
            v
+-------------------------+
|     Thalamus Engine     |
|   (Controller / Brain)  |
+-----------+-------------+
            |
            v
+-------------------------+
|     OpenMemory DB       |
| (Vectors + Temporal KG) |
+-----------+-------------+
            |
            v
+-------------------------+
|      Local LLM Model    |
|   (Ollama / GGUF / API) |
+-------------------------+
```

All components run locally; no cloud dependencies are required.

---

# 2. Component Responsibilities

## 2.1 Local UI (Qt6)
The UI should remain thin:

- Display chat history  
- Send user messages to Thalamus  
- Show Thalamus responses from **AnswerCall**  
- Provide menu/settings for model, memory, logs  
- Offer file importer to feed documents into memory  
- Show advanced debug info (retrieval plan, stored memories, etc.)  

The UI **does not** run logic; it simply calls Thalamus via:

```python
reply = thalamus.run_turn(user_message)
```

---

# 3. Thalamus Engine

The Thalamus Engine is the core orchestrator. It:

- Receives the user message  
- Gathers context + persona + memory  
- Runs a structured 3‑call cycle:  
  - **AnswerCall** → assistant response  
  - **ReflectCall** → new memories to store  
  - **RetrieveCall** → instructions for next‑turn memory fetching  
- Manages OpenMemory read/write  
- Maintains the chat history snippet  
- Stores and loads persona context  

It exposes a stable API:

```
run_turn(message) -> assistant_reply
reset_session()
export_memory()
import_document()
```

---

# 4. Memory Pipeline

## 4.1 AnswerCall
Inputs:
- User message  
- Persona memories  
- Retrieved context  
- Recent dialog  

Output:
- **Natural‑language assistant response**

AnswerCall may *not* write memory, change settings, or produce JSON.

---

## 4.2 ReflectCall
ReflectCall examines the assistant message and conversation context to produce **memory objects**.

Example output:

```json
{
  "memories_to_store": [
    {
      "type": "user_identity",
      "content": "User works aboard the Amazon Conqueror.",
      "topic": "personal_background",
      "importance": "high"
    }
  ]
}
```

The Thalamus Engine stores these directly into OpenMemory.

Temporal facts are stored using:

- subject  
- predicate  
- object  
- valid_from (optional)  

OpenMemory automatically manages fact histories.

---

## 4.3 RetrieveCall
RetrieveCall determines **what memories should be loaded next turn**, producing a JSON retrieval plan.

Example:

```json
{
  "retrieval_instructions": [
    {
      "mode": "memory",
      "topic": "assistant_identity",
      "types": ["persona"],
      "limit": 8
    }
  ]
}
```

Thalamus executes the plan at the *start of the next turn*, collecting:

- Persona memories  
- Identity  
- Preferences  
- Task summaries  
- Project state  
- Temporal facts  

Then these are injected into the next AnswerCall.

---

# 5. Integration Between UI & Thalamus

## 5.1 Typical flow

```
UI → Thalamus.run_turn(message)
  → Execute retrieval plan (load memory)
  → AnswerCall
  → return response to UI
  → ReflectCall
  → store memories
  → RetrieveCall
  → save retrieval plan
```

Only the AnswerCall result is ever shown to the user.

The UI may optionally display:

- retrieved memories  
- stored memories  
- debug info  

but these are not part of the normal conversation view.

---

# 6. Data Storage

## 6.1 Chat history
Stored as a JSON array of:

```json
{ "role": "assistant", "content": "..."}
```

Only the last N messages (configurable) become “recent dialog”.

---

## 6.2 OpenMemory entries

Each memory carries:

- `content` (semantic text)  
- `vector` (embedding)  
- `metadata`:
  - `userId`
  - `topic`
  - `type`
  - `importance`
  - `persona_related`
  - `created_at`

Temporal facts use:

- `subject`
- `predicate`
- `object`
- `valid_from`
- `valid_to` (OpenMemory sets automatically)

---

# 7. UI Features

## 7.1 Main Chat Window  
Shows only the AnswerCall output.

## 7.2 Debug Console  
Can show:

- Retrieval plan  
- Memory fetch results  
- ReflectCall JSON  
- Stored temporal facts  
- Raw LLM prompts (optional)  
- Errors  

## 7.3 Memory Browser  
Lets the user inspect:

- Persona sets  
- Project memories  
- Timeline of temporal facts  
- Search by topic/type  

## 7.4 Settings  
Allows user to set:

- Memory on/off  
- Model selection (LLM backend)  
- Verbosity of logs  
- Toggle debug panels  
- Reset session / memory database  

## 7.5 Document Import  
User drops a PDF or text file, UI calls:

```python
thalamus.ingest_document(path)
```

Thalamus:

- Splits into chunks  
- Generates summaries  
- Adds topic/type metadata  
- Stores into OpenMemory  

---

# 8. Error Handling

- Invalid JSON from the LLM is caught and logged  
- Retrieval failures fall back to minimal context  
- Memory writes are validated  
- Chat history repairs itself when malformed  
- All crashes are surfaced to UI  

---

# 9. Future Extensions

- Tool calling (sandboxed local tools)  
- Multiple persona modes  
- Multi-model routing (different LLMs per task)  
- User profile customization  
- Voice I/O  

---

# 10. Summary

LLM‑Thalamus + Local UI form a cohesive local AI assistant with:

- Persistent identity  
- Long‑term memory  
- Strong project recall  
- Fully offline operation  
- Extensible modular architecture  
- Structured memory management (Answer → Reflect → Retrieve)

This design allows Gwen (your local LLM persona) to grow continuously and safely through controlled memory ingestion and retrieval.

---

**Document Version:** 1.0  
**Format:** Markdown  
