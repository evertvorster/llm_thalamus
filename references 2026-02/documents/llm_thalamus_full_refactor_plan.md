# llm-thalamus Refactor Master Plan (Detailed Session Summary)

This document provides a full, explicit technical summary of:
- The overall architectural plan for llm-thalamus
- The implementation details already completed
- Exact file-level changes made in this session
- The next detailed steps
- The ultimate long-term design vision

It is designed to be loaded at the start of the next session to immediately restore project context.

---

# 1. OVERALL ARCHITECTURAL PLAN

llm-thalamus is evolving from a single large controller (`llm_thalamus.py`) into a modular runtime with:

## 1.1 Core Concepts
### A. **Per-call API**
Each LLM operation is a **named call**:  
- `answer`
- `reflection`
- `space_answer`
- `space_reflect`
- `plan`
- `understand`
- `execute`

Each call is controlled via:
```
thalamus.calls.<call_name>.{prompt_file, max_memories, max_messages, flags}
```

### B. **Template-Based Behavior**
All call text is stored in:
```
config/prompt_<call_name>.txt
```
The Python code only fills tokens such as:
```
__NOW__
__USER_MESSAGE__
__OPEN_DOCUMENTS_INDEX__
__OPEN_DOCUMENTS_FULL__
__MEMORY_LIMIT__
__MEMORIES_BLOCK__
__HISTORY_MESSAGE_LIMIT__
__CHAT_HISTORY_BLOCK__
```

### C. **Slim Thalamus Core**
`llm_thalamus.py` becomes:
- A **dispatcher**
- A **data assembler**
- A thin wrapper for:
  - memory retrieval
  - history retrieval
  - document collection
  - LLM interaction

### D. **Loaders**
All templates are loaded using:
```
Thalamus._load_prompt_template(call_name)
```
defined in `llm_thalamus.py`.

### E. **Module Decomposition Roadmap**
Eventually llm_thalamus.py will be split into:
```
llm_thalamus/
    core.py              # dispatcher + entrypoints
    call_engine.py       # answer, reflection, future calls
    memory_adapter.py    # wraps OpenMemory
    history.py           # conversation history logic
    template_loader.py   # file loader + token substitution
    model_client.py      # Ollama interface
```

---

# 2. WHAT WE ACHIEVED IN THIS SESSION (EXPLICIT FILE-LEVEL CHANGELOG)

This details exactly what was changed, at the file level.

## 2.1 `llm_thalamus.py`

### A. Removed massive inline reflection prompt
- The entire multiline string in `_call_llm_reflection` was removed.
- It now uses:
```
template = self._load_prompt_template("reflection")
```
with token substitution.

### B. Removed massive inline answer prompt
- `_call_llm_answer` now constructs dynamic data blocks only.
- All instructional text moved to:
```
config/prompt_answer.txt
```

### C. Added token substitution for answer:
```
template.replace("__NOW__", now)
.replace("__OPEN_DOCUMENTS_INDEX__", open_docs_index)
.replace("__OPEN_DOCUMENTS_FULL__", open_docs_full)
.replace("__MEMORY_LIMIT__", str(memory_limit))
.replace("__MEMORIES_BLOCK__", memories_for_template)
.replace("__HISTORY_MESSAGE_LIMIT__", str(history_message_limit))
.replace("__CHAT_HISTORY_BLOCK__", history_for_template)
.replace("__USER_MESSAGE__", user_message)
```

### D. Added helper methods:
```
def _get_call_config(self, name: str) -> CallConfig
def _load_prompt_template(self, call_name: str) -> Optional[str]
```

### E. Answer + Reflection no longer embed prompt logic in Python
Only fallback stubs remain.

### F. Per-call message limits
Answer and reflection now use:
```
calls.answer.max_messages
calls.reflection.max_messages
```

### G. Per-call memory limits
Answer call uses:
```
calls.answer.max_memories
```

Reflection currently does not use memory retrieval (intentional).

---

## 2.2 `config.json`

### A. Added unified block:

```
"thalamus": {
  "calls": {
    "answer": {
      "prompt_file": "config/prompt_answer.txt",
      "max_memories": 20,
      "max_messages": 10,
      "flags": {}
    },
    "reflection": {
      "prompt_file": "config/prompt_reflection.txt",
      "max_memories": 0,
      "max_messages": 5,
      "flags": {}
    }
  }
}
```

### B. Removed obsolete `"prompts"` block.

---

## 2.3 New Template Files (Runtime dependencies)

### A. `config/prompt_answer.txt`
Full instruction set for answer call.

### B. `config/prompt_reflection.txt`
Full instruction set for reflection call.

Both files are required at runtime and must be installed.

---

# 3. NEXT IMMEDIATE STEPS (DETAILED)

These are the exact next moves for the next session:

## STEP 1 — Update Makefile safely
- Add installation lines for new template files:
```
install -d "$(DESTDIR)$(LIBDIR)/config"
install -m644 config/prompt_answer.txt "$(DESTDIR)$(LIBDIR)/config/"
install -m644 config/prompt_reflection.txt "$(DESTDIR)$(LIBDIR)/config/"
```
No other changes should be made until we see the real Makefile in the next session.

## STEP 2 — Begin extraction of components
Start small:

### 2A. Extract template loader into:
```
llm_thalamus/template_loader.py
```

### 2B. Extract history logic into:
```
llm_thalamus/history.py
```

### 2C. Extract memory logic into:
```
llm_thalamus/memory_adapter.py
```

After each extraction:
- Update imports
- Run LLM locally
- Verify answer + reflection still work

## STEP 3 — Introduce dispatcher-level API
Add:

```
def dispatch_call(self, call_name: str, payload: dict) -> CallResult:
```

This will eventually replace direct calls to `_call_llm_answer` inside `process_user_message`.

## STEP 4 — Rewrite `process_user_message`
Turn it into:

```
# 1. Answer call
result = self.dispatch_call("answer", {...})

# 2. Reflection call (if enabled)
self.dispatch_call("reflection", {...})

return result.text
```

Simplest possible structure.

---

# 4. THE ULTIMATE GOAL (ARCHITECTURAL NORTH STAR)

The final architecture should look like this:

```
thalamus_worker.py
    |
    |--calls--> Thalamus.dispatch_call()
                     |
                     |--uses--> CallEngine
                     |              |
                     |              |--loads template
                     |              |--fills tokens
                     |              |--retrieves memories
                     |              |--retrieves history
                     |
                     |--uses--> MemoryAdapter
                     |--uses--> ConversationHistory
                     |--uses--> TemplateLoader
                     |
                     |--returns--> CallResult
```

## Pillars of the final design

- **Fully modular** — each subsystem isolated.
- **Template-driven** — behavior editable without Python.
- **Per-call API** — clean extension for future capabilities.
- **Thin core** — llm_thalamus.py orchestrates, not implements.
- **Extensible** — space calls, plan/understand/execute are trivial to add.
- **Stable** — fewer large files reduces context loss and session risk.
- **Packaging-friendly** — consistent file layout under `/usr/lib/llm_thalamus`.

---

# 5. FILE LOCATIONS (REFERENCE)

```
/usr/lib/llm_thalamus/
    llm_thalamus.py
    config/
        prompt_answer.txt
        prompt_reflection.txt
    templates/        (future)
    core.py           (future)
    call_engine.py    (future)
    history.py        (future)
    memory_adapter.py (future)
    template_loader.py(future)
```

---

# 6. WHAT TO DO AT THE START OF NEXT SESSION

1. Upload:
   - `Makefile`
   - `llm_thalamus.py`
   - `config.json`

2. We will:
   - Patch Makefile safely  
   - Start first extraction module (template_loader.py)

3. Then continue the decomposition step-by-step.

---

# END OF DOCUMENT
