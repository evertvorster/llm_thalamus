# llm_thalamus audit appendix

## A) Snapshot caveats

### A.1 Hidden-directory mismatch

The prompt included a `tree -a` listing with:
- `.continue/...`
- `.vscode/`

Those directories were not present in the uploaded archive extracted for this audit. Therefore:
- they are not included in the complete per-file inventory
- their contents are unknown from snapshot
- any architecture they imply should not override the code archive

### A.2 Bundled docs are stale

The archive contains:
- `resources/Documentation/audit_overview.md`
- `resources/Documentation/audit_file_inventory.md`
- `resources/Documentation/audit_appendix.md`
- `README_developer.md`

These documents describe nodes and files that do not exist in the current shipped graph. They are useful as design history, but not as current architecture truth.

## B) Current graph in one glance

```text
context.bootstrap
  purpose: mechanical prefill only
  prompt: none
  tools: chat_history_tail, memory_query
  output: context.sources seed

llm.context_builder
  purpose: gather context + decide next
  prompt: resources/prompts/runtime_context_builder.txt
  tools: chat_history_tail, memory_query, world_apply_ops
  output: context.next, context.sources, maybe state.world

llm.answer
  purpose: user-facing answer
  prompt: resources/prompts/runtime_answer.txt
  tools: none
  output: final.answer + assistant stream

llm.reflect
  purpose: topic maintenance + memory store
  prompt: resources/prompts/runtime_reflect.txt
  tools: world_apply_ops, memory_store
  output: maybe state.world + runtime.reflect_result
```

## C) Prompt token table

Defined centrally in `src/runtime/nodes_common.py:GLOBAL_TOKEN_SPEC`.

Visible token names:
- `USER_MESSAGE`
- `WORLD_JSON`
- `TOPICS_JSON`
- `CONTEXT_JSON`
- `EXISTING_CONTEXT_JSON`
- `NOW_ISO`
- `NOW`
- `TIMEZONE`
- `TZ`
- `STATUS`
- `ISSUES_JSON`
- `ASSISTANT_ANSWER`
- `ASSISTANT_MESSAGE`
- `REQUESTED_LIMIT`
- `NODE_ID`
- `ROLE_KEY`

Implication:
- adding a new placeholder is a code change, not just a prompt change

## D) Notable exact code relations

- `src/llm_thalamus.py` imports `config.bootstrap_config`, `controller.worker.ControllerWorker`, and `ui.main_window.MainWindow`.
- `src/controller/worker.py` imports `runtime.deps.build_runtime_deps`, `runtime.langgraph_runner.run_turn_runtime`, and `runtime.state.new_runtime_state`.
- `src/runtime/langgraph_runner.py` imports `runtime.graph_build.build_compiled_graph`.
- `src/runtime/graph_build.py` imports `runtime.registry.get` and constructs nodes by calling `get(...).make(deps, services)`.
- `src/runtime/nodes/llm_context_builder.py` calls `run_controller_node(...)` from `src/runtime/nodes_common.py`.
- `src/runtime/nodes/llm_reflect.py` also calls `run_controller_node(...)`.
- `src/runtime/nodes/llm_answer.py` calls `run_streaming_answer_node(...)`.
- `src/runtime/tools/toolkit.py` instantiates `StaticProvider(resources)` and builds a `ToolSet` from node skill policy + enabled skills.
- `src/runtime/tools/providers/static_provider.py` binds tool definitions to handlers from `src/runtime/tools/bindings/*`.
- `src/runtime/tools/bindings/memory_query.py` calls `resources.mcp.call_tool("openmemory", name="openmemory_query", ...)`.
- `src/runtime/tools/bindings/memory_store.py` calls `resources.mcp.call_tool("openmemory", name="openmemory_store", ...)`.

## E) Known stale or spike-oriented files

Likely stale or spike/probe oriented:
- `src/runtime/graph_policy.py`
- `src/runtime/prompt_loader.py`
- `src/runtime/build.py`
- `src/runtime/tools/registry.py`
- most of `src/tests/*`
- `README_developer.md`
- `resources/Documentation/*`
