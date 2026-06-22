---
title: pi RPC — Signal Mapping & Implementation Plan
type: plan
created: 2026-06-22
updated: 2026-06-22
status: draft
---

# pi RPC ↔ llm-thalamus UI Signal Mapping

## Signals to Keep

| UI Signal | pi RPC Source | Status |
|-----------|--------------|--------|
| assistant_stream_start | turn_start / message_start | ✅ Keep |
| assistant_stream_delta | message_update.text_delta | ✅ Keep |
| assistant_stream_end | message_end | ✅ Keep |
| thinking_started | message_update.thinking_start | ✅ Keep |
| thinking_delta | message_update.thinking_delta | ✅ Keep |
| thinking_finished | message_update.thinking_end | ✅ Keep |
| busy_changed | agent_start / agent_end | ✅ Keep |
| error | auto_retry_end failure | ✅ Keep |
| history_turn | get_messages response | ✅ Keep |
| activity_event (tool) | tool_execution_start/end | ✅ Keep, simplified |

## Signals to Drop

assistant_message (legacy), log_line, world_committed/updated, state_updated, prompt_*, tool_approval_requested

## PiRPCBridge Sketch

```python
class PiRPCBridge(QObject):
    assistant_stream_start = Signal()
    assistant_stream_delta = Signal(str)
    assistant_stream_end = Signal()
    thinking_started = Signal()
    thinking_delta = Signal(str)
    thinking_finished = Signal()
    busy_changed = Signal(bool)
    error = Signal(str)
    history_turn = Signal(str, str, str)

    def start(self, session_path=None):
        env = {**os.environ, "PI_CODING_AGENT_DIR": cfg_dir, "PI_OFFLINE": "1"}
        self._proc = subprocess.Popen(
            ["pi", "--mode", "rpc"] + (["--session", session_path] if session_path else []),
            env=env, stdin=PIPE, stdout=PIPE, text=True)
        self._reader = Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def submit_message(self, text, images=None): ...
    def send_command(self, cmd): ...
    def load_history(self): ...
    def shutdown(self): ...
```

## Session Management

List sessions: read ~/.pi/agent/sessions/ from filesystem
Load session: {"type": "switch_session", "sessionPath": "..."}
Start fresh: {"type": "new_session"}
Get info: {"type": "get_state"}
Fork: {"type": "fork", "entryId": "..."}
Clone: {"type": "clone"}

## Command Registry

Built-in RPC commands: model, new, compact, fork, clone, name, export, abort
Pi commands: discovered via get_commands on startup
