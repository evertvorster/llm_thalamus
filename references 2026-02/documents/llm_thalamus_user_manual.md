# llm-thalamus – User Manual

## 1. What llm-thalamus Is

`llm_thalamus` is the orchestration engine that connects your local LLM, the Thalamus memory system, the Spaces/Objects/Versions document manager, and the UI into a single coherent “local brain.”

Its core responsibilities are:

- Build a **controlled, repeatable prompt pipeline** for your local LLM.
- Retrieve relevant long‑term memory from **OpenMemory**.
- Inject **active documents** from the currently entered Space.
- Perform **reflection** so the LLM can extract new facts and store them as memories.
- Manage chat history and conversation context.
- Coordinate with the **Thalamus UI** for status updates, logs, and display controls.

Where the *Spaces & Memory Manager* controls **what** the LLM sees,  
**llm-thalamus defines *how* the LLM thinks.**

---

## 2. Conceptual Overview

llm-thalamus acts as the **central nervous system** of your AI:

```
User → UI → Thalamus → LLM
                 ↘→ OpenMemory
```

### 2.1 What the LLM Receives

Each time you send a message, llm-thalamus composes a structured prompt containing:

1. **Recent conversation history**
2. **Active documents** from the current Space  
   (See the _Thalamus Spaces User Guide_ for details)
3. **Retrieved memory items** from OpenMemory
4. **System instructions and behavioral constraints**
5. **User message**

This ensures your LLM:

- Has exactly the context it needs  
- Never gets flooded with irrelevant data  
- Remains consistent across long-term use  
- Avoids hallucinating from stale or incorrect memory  

### 2.2 What llm-thalamus Stores

After generating an answer, llm-thalamus runs a **reflection phase**, where the LLM inspects its own reply to decide:

- Should a new memory be stored?
- Should an existing memory be updated?
- Is the reply just chit-chat (no storage necessary)?

This process avoids:

- Oversized memory databases  
- Repeated or redundant facts  
- Storing private/sensitive data unintentionally  

---

## 3. UI Overview

The UI consists of three major components:

---

### 3.1 The Chat Window

This is your primary interaction area.

Features:

- Markdown‑rendered replies  
- Code blocks and LaTeX rendering  
- Switchable raw/processed views  
- Scroll‑back history  
- Chat log automatically saved via Thalamus  

Best practice:

- Ask questions naturally; llm-thalamus automatically adds the right context.  
- When referencing a document, use its filename — the LLM will recognize it.  
- When switching projects, **enter the correct Space** first so only relevant docs are loaded.

---

### 3.2 The Thalamus Log Panel

Accessible by clicking the "brain" icon.

Shows:

- Memory retrieval decisions  
- Document injection details  
- Reflection output  
- Any warnings or errors from the Thalamus pipeline  
- Performance and timing info  

Use this panel when:

- The LLM seems to ignore a document  
- Memory retrieval appears incorrect  
- Something feels “off” in the reasoning  
- Debugging advanced behavior  

This is the window into the black box.

---

### 3.3 The Spaces & Memory Manager

This system is documented in detail in:

**`thalamus_spaces_user_guide.md`**

llm-thalamus uses this as the *source of truth* for:

- Which documents exist  
- Which versions are active  
- Which project is currently active  
- What text to inject into the LLM  

If the LLM appears to be using the wrong information,  
99% of the time the solution involves:

- Switching to the correct Space  
- Activating the correct version  
- Deactivating outdated documents  

---

## 4. How to Work With llm-thalamus

### 4.1 Switching Projects

Each project should live in its own **Space**.

Before you talk to the LLM about that project:

1. Open the Spaces panel  
2. Enter the correct Space  
3. Confirm the active objects/versions  

Now llm-thalamus only injects documents from that Space.

This prevents cross‑contamination between:

- Work tasks  
- Technical projects  
- Personal notes  
- Experiments  

---

### 4.2 Training the LLM

This system supports **two kinds of training**:

---

#### **A) Document-based training (preferred)**

Simply ingest documents into Spaces.

The LLM learns:

- Terminology  
- Architecture  
- Requirements  
- Patterns  
- History  
- Project knowledge  

This is the strongest and most reliable form of training.

---

#### **B) Conversational training (stored via reflection)**

When the LLM discovers:

- A fact  
- A preference  
- A rule  
- A permanent detail  

…llm-thalamus’s reflection layer stores it into OpenMemory.

Examples:

- “My laptop is an ASUS ROG.”  
- “Dynamic Power Daemon runs as root.”  
- “Namibia has excellent astrophotography conditions.”  

These memories fade naturally unless reinforced in multiple conversations.

---

### 4.3 Asking the LLM to recall project docs

Simply say:

- “Summarize the active documents.”  
- “List the key requirements.”  
- “Explain the architecture as you understand it.”  
- “OpenMemory: what do you know about `design_overview.md`?”  

llm-thalamus automatically retrieves everything.

---

### 4.4 Keeping the Database Clean

Regularly perform:

- Delete old document versions  
- Remove unused spaces  
- Deactivate documents that shouldn't be injected  
- Make sure filenames remain stable  

The LLM performs best when the injected context is **clean and relevant**.

---

## 5. When Something Goes Wrong

### Symptom: LLM ignores documents
Check:

- Did you enter the correct Space?  
- Is the object active?  
- Is the correct version active?  

### Symptom: LLM's answers seem outdated
Check:

- Old version still active  
- Deleted versions not cleaned  
- LLM hasn’t seen the newly ingested version  

### Symptom: Memory retrieval seems wrong
Open the **Thalamus Log** and look for:

- Retrieval plan  
- Number of retrieved items  
- Whether memory was classified properly  
- Whether reflection ran successfully  

### Symptom: LLM is confused after long sessions
Try:

1. Clear the conversation  
2. Keep the important docs active  
3. Ask:  
   **“Please reset your short-term context.”**  

### Symptom: UI issues
Check:

- Spaces DB may require refreshing  
- Restart the application  
- File permissions on config or memory path  

---

## 6. Best Practices for Working With llm-thalamus

### ✔ Keep one Space per project  
The LLM becomes dramatically more reliable.

### ✔ Keep only one active version per object  
Avoids contradictory context.

### ✔ Write documents for the LLM  
Clear, well‑structured docs yield far better reasoning.

### ✔ Use reflection sparingly  
If the LLM begins storing unnecessary memories, disable or tune it.

### ✔ Start new conversations when switching topics  
The pipeline is optimized for focused sessions.

### ✔ Periodically prune memory  
OpenMemory can store a lot, but **quality beats quantity**.

---

## 7. Troubleshooting Deep Issues

### 7.1 Corrupted Spaces DB
If objects don’t appear:

- Close application  
- Remove `spaces.db` from the OpenMemory directory  
- Re-ingest documents  

### 7.2 Broken OpenMemory installation
Check:

```
python -c "import openmemory; print(openmemory.__version__)"
```

Or manually run:

```
from openmemory import OpenMemory
OpenMemory("path/to/memory.sqlite")
```

### 7.3 LLM model mismatch
Ensure your local model:

- Supports sufficient context window  
- Works with your GPU  
- Matches the prompt format used by llm-thalamus  

### 7.4 Debugging the Thalamus Engine
Enable verbose logging in the config, then restart Thalamus UI.

---

## 8. Summary

llm-thalamus provides:

- A robust prompting pipeline  
- Clean integration with tool use and memory  
- A controlled way to expose project documents to the LLM  
- A reproducible architecture for long-term knowledge retention  
- A UI that simplifies the entire process  

The system works best when:

- Spaces are clean  
- Objects are meaningful  
- Versions are consistent  
- Active context is limited to the task at hand  

With these practices, llm-thalamus becomes a **true personal cognitive layer** running entirely on your machine.

