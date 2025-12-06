# llm-thalamus UI Design Document (Initial Version)

## 1. Overview

This document describes the initial user interface design for the **llm-thalamus** project.  
The UI is built using **PySide6** and is responsible for:

- Displaying conversation between user and LLM  
- Showing system status for the LLM, Thalamus orchestration engine, and Memory subsystem  
- Displaying internal Thalamus control traffic  
- Automatically saving chat history  
- Optionally logging raw thalamus events  

The UI must function **before thalamus is connected**, and become fully interactive once thalamus begins emitting events.

This version covers:

- Chat Pane  
- Dashboard  
- Thalamus Control Pane  
- Chat History System  
- Logging Behavior  
- Event Model Used by the UI  

---

## 2. Main Window Layout

The UI consists of three primary visible elements:

1. **Dashboard** — a horizontal strip of “control lights”  
2. **Chat Pane** — main conversation area  
3. **Thalamus Control Pane** — optional slide-in area showing internal wiring logs  

### 2.1 Layout Diagram

```
+--------------------------------------------------------------+
| Dashboard (LLM • Thalamus • Memory lights)                   |
+--------------------------------------------------------------+
| Chat Pane (scrollable conversation)                          |
|                                                              |
|   [ previous session history (loaded at startup) ]           |
|   --------------------------------------------------         |
|   [ current session chat messages ]                          |
|                                                              |
|  ------------------------------------------------------------|
|  [ Input Field ..................... ]   [ Send ]            |
+--------------------------------------------------------------+

Thalamus Control Pane (toggles via Thalamus light)
+--------------------------------------------------------------+
|  Internal thalamus control text for this session             |
|  Scrollable                                                   |
|  [ Save log button ]                                         |
+--------------------------------------------------------------+
```

---

## 3. Dashboard Design

The dashboard is a narrow strip at the top (or bottom) of the window showing three status indicators:

### 3.1 Status Lights

| Subsystem | States | Description |
|----------|---------|-------------|
| **LLM** | disconnected, idle, busy, error | State of LLM adapter calls |
| **Thalamus** | disconnected, connected, busy, error | Clickable; opens control pane |
| **Memory** | disconnected, idle, busy, error | For memory queries/writes |

### 3.2 Behavior Before Thalamus Is Connected

- Thalamus light = **dark/disconnected**
- LLM + Memory lights = **dark**
- Chat **Send** button disabled
- Chat pane still loads previous session history

### 3.3 Behavior When Thalamus Connects

- Thalamus light turns **solid (connected)**
- LLM + Memory lights turn on as applicable
- Send button is enabled

### 3.4 Busy Indication

- Light blinks/pulses when subsystem is processing:
  - LLM call in flight
  - Memory retrieval or write
  - Thalamus orchestrating between subsystems

---

## 4. Chat Pane Design

### 4.1 Message Flow

Chat messages come from **thalamus only** — never directly from the LLM or UI.

The UI receives events that include:

- User messages  
- Assistant messages (LLM responses)  
- System messages (only if thalamus emits them)

### 4.2 Rendering Rules

- Display raw text emitted from thalamus with **no mutation**.
- Support:
  - LaTeX in `\[ ... \]` form
  - Code blocks fenced with triple backticks
- Renderer must never modify original text; only style it visually.

### 4.3 Raw vs Rendered View

Global toggle:

```
[ Raw ]   [ Rendered ]
```

- **Raw** = exact string from thalamus, monospaced, no formatting  
- **Rendered** = styled code blocks, styled LaTeX markers (backslashes preserved)

### 4.4 Input

- Multi-line input field  
- Enter = send  
- Shift+Enter = newline  
- Send button mirrors Enter  

---

## 5. Chat History System

Chat history is **always saved** automatically.

### 5.1 Per-session Saving

When a new session starts:

- UI opens a new file in:  
  `chat_history/session-<timestamp>.log`

Every `chat_message` event gets appended.

### 5.2 Loading Previous Session

On UI startup:

- Load **previous session’s file**
- Render it at the **top** of the chat pane as “previous chat”
- Do **NOT** prepend previous chat to the new log file
- Current session starts empty beneath it

A future UI feature will allow browsing older files.

---

## 6. Thalamus Control Pane

### 6.1 Activation

- Toggle by **clicking the Thalamus dashboard light**
- Opens a side or bottom pane containing raw control text

### 6.2 Contents

Displays **all thalamus control events** for the current session:

- Retrieval-plan prompts and results  
- Reflection prompts and results  
- Memory queries and responses  
- Other internal orchestration text  

All entries are displayed in:

- Chronological order  
- Monospace  
- Scrollable buffer  
- Grouped by turn if desired

### 6.3 Saving Behavior

- Pane includes a **Save** button:
  - Always available, regardless of logging setting
  - Writes the entire in-memory control-pane text to a timestamped file in `/log`

---

## 7. Thalamus Logging System

Logging is controlled via a config flag.

### 7.1 Auto Logging Enabled

If `logging.thalamus_enabled == true`:

- On `session_started`, open file:  
  `log/thalamus-<timestamp>.log`

- Every `thalamus_control_entry` is appended as raw text

### 7.2 Auto Logging Disabled

- Nothing is written automatically  
- User may still click **Save** to export the current pane contents to a file

---

## 8. Event Types (Thalamus → UI)

The UI listens for structured events from thalamus.

### 8.1 Chat Message

```
event_type: "chat_message"
payload:
  role: "user" | "assistant"
  turn_id: int
  content: string (raw)
```

### 8.2 Status Update

```
event_type: "status_update"
payload:
  subsystem: "llm" | "thalamus" | "memory"
  status: "disconnected" | "connected" | "idle" | "busy" | "error"
  detail: optional string
```

### 8.3 Thalamus Control Entry

```
event_type: "thalamus_control_entry"
payload:
  turn_id: int
  direction: "outbound" | "inbound"
  target: "llm" | "memory"
  step: "retrieval_plan" | "answer" | "reflection" | "memory_query" | "memory_write"
  raw_text: string (unaltered control text)
```

### 8.4 Session Lifecycle

```
event_type: "session_started"
event_type: "session_ended"
```

---

## 9. Behavior Summary

### On Startup:

- Load previous chat history into chat pane (read-only)
- Show dashboard with thalamus light dark
- Send button disabled

### When Thalamus Connects:

- Emit `session_started`
- Dashboard updates
- Input enabled
- New chat_history + optional new log file opened

### During Use:

- Chat events populate the chat pane + history file  
- Control events populate control pane + optional log  
- Dashboard updates reflect subsystem states  

### On Shutdown / Session End:

- Emit `session_ended`
- Close chat and log files  
- UI returns to “waiting for thalamus” mode  

---

## 10. Future Extensions (Not in initial UI)

- Audio STT/TTS  
- File ingestion from UI  
- Image display for generated diffusion outputs  
- Memory browser  
- Settings dialog  
- Model switching  
- Multi-tab sessions  
- Full markdown renderer + KaTeX  

The initial UI focuses only on:  
**Chat, dashboard, thalamus control pane, logging, and session history.**
