
# llm-thalamus UI Design Document

**File:** `llm_thalamus_ui.py`  
**Version:** 2025-12-05  
**Project:** llm-thalamus  
**Purpose:** Provide a user interface for interacting with the Thalamus backend.

---

# 1. Overview

The UI is a PySide6 application that:

- Displays assistant and user messages  
- Shows system status (LLM, memory, Thalamus)  
- Allows message entry  
- Displays internal Thalamus debug logs  
- Stores chat logs as searchable JSON  
- Auto-starts and manages the Thalamus backend  

The UI performs **no computation** and contains **no LLM logic**.

---

# 2. Responsibilities

1. **Chat interface**
2. **Status lights and subsystem indicators**
3. **Debug dock for Thalamus internal logs**
4. **Session-based log saving**
5. **Configuration awareness**
6. **Automatic Thalamus loading**

---

# 3. Layout Structure

## 3.1 Main Window Layout

```
+------------------------------+
| Status Lights: T L M         |
+------------------------------+
| Chat Display (raw/rendered)  |
+------------------------------+
| Input box + Send button      |
| Config | Quit                |
+------------------------------+
| Dock: Thalamus Control Log   |
+------------------------------+
```

The dock is collapsible and toggled by clicking the **Thalamus status light**.

---

# 4. Status Indicators

Three circular lights represent:

| Subsystem | States | Meaning |
|-----------|--------|---------|
| Thalamus  | disconnected, connected, busy, error | Backend availability |
| LLM       | same | Status during answer/reflection |
| Memory    | same | Status during retrieval/store |

Color coding:

- **Green** — good  
- **Yellow** — busy  
- **Red** — error  
- **Gray** — disconnected  

---

# 5. Chat Display

- Supports **raw** and **rendered** modes  
- Shows JSON logs under the hood (saved in `chat_history/`)  
- Multi-line input box  
- Enter or Ctrl+Enter sends a message  

All messages are timestamped.

---

# 6. Debug Dock (Thalamus Control Panel)

Displays:

- Prompt payloads  
- Memory retrieval blocks  
- Reflection outputs  
- Internal status messages  
- Errors and warnings  

This allows full transparency into the Thalamus pipeline.

A “Save Log…” button exports everything in the dock.

---

# 7. Thalamus Integration

The UI loads Thalamus dynamically:

```
spec = importlib.util.spec_from_file_location(...)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
th = module.Thalamus()
```

The UI then connects event handlers:

- chat messages → chat panel  
- status updates → status lights  
- debug entries → control dock  
- session start/end → UI indicators  

If import fails:

- Red Thalamus light  
- Send disabled  
- Error text printed to dock  

---

# 8. Configuration

The UI reads from `config/config.json`:

```json
"ui": {
    "auto_connect_thalamus": true,
    "show_raw_messages": false
}
```

Future UI settings will be added here.

---

# 9. Logging

### Chat Logs
Stored in:
```
chat_history/session-<timestamp>.log
```

Format:
```json
{ "timestamp": "...", "role": "user", "content": "..." }
```

### Thalamus Logs
Session logs appear in the debug dock and may be saved separately.

---

# 10. Extensibility

The UI is designed to easily accommodate:

- Additional status lights (for STT/TTS, SD, CV modules)  
- Additional dock widgets  
- Configurable themes  
- Model selection  
- Memory browser  
- Tool panels (e.g., SD image generation UI)  

UI communicates exclusively through event callbacks, so backend changes do not break UI code.

---

# 11. Conclusion

The llm-thalamus UI provides:

- A clean interface for interacting with Thalamus  
- Full transparency into internal operations  
- A foundation for advanced assistant tooling  

It is intentionally minimal and designed for extensibility.
