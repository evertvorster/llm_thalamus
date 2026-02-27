# llm_thalamus Audit Appendix

## A1) Unknowns from snapshot (and what would confirm them)

1. **Where `world_state.json` is committed after `world_apply_ops`.**
   - Evidence: `runtime.tools.bindings.world_apply_ops` returns mutated world but does not call `controller.world_state.commit_world_state()`.
   - Confirm by: searching for `commit_world_state(` call sites and verifying end-of-turn logic in `controller.worker.py` / UI.

2. **Chat history JSONL schema and append behavior.**
   - Confirm by: inspecting `var/llm-thalamus-dev/data/chat_history.jsonl` and `controller.chat_history_service.FileChatHistoryService` write path.

3. **Event bus wiring and where events are persisted (if at all).**
   - Confirm by: tracing `runtime.event_bus.EventBus` usage and UI subscription.

4. **Packaging/installation entrypoints.**
   - Confirm by: including packaging metadata in future snapshots (e.g., `pyproject.toml`) or documenting external launcher scripts.

## A2) Static search notes

- The string `project_status` appears only in:
  - `README.md`
  - `README_developer.md`
  - `resources/Documentation/audit_overview.md`
  No compiler/runtime implementation is present in `src/` in this snapshot.

## A3) Short excerpts (≤ 10 lines)

### Graph topology (from `src/runtime/graph_build.py`)

```python
g.set_entry_point("router")
g.add_conditional_edges("router", route_selector, {...})
g.add_conditional_edges("context_builder", context_next_selector, {...})
g.add_edge("memory_retriever", "context_builder")
g.add_edge("world_modifier", "answer")
g.add_edge("answer", "reflect_topics")
g.add_edge("reflect_topics", "memory_writer")
g.add_edge("memory_writer", END)
```

### Tool loop “formatting pass” idea (from `src/runtime/tool_loop.py`)

```python
if not tool_calls:
    if response_format is None:
        yield StreamEvent(type="done", meta={}); return
    # final formatting pass (tools disabled)
    final_req = ChatRequest(... tools=None, response_format=response_format, stream=True)
```

