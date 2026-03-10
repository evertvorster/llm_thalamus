Place these files at the matching repo-relative paths under your `src/` tree.

New files:
- `src/runtime/tools/descriptor.py`
- `src/runtime/tools/providers/base.py`
- `src/runtime/tools/providers/local_provider.py`
- `src/runtime/tools/providers/mcp_provider.py`

Updated files:
- `src/runtime/tools/resources.py`
- `src/runtime/tools/toolkit.py`
- `src/runtime/tool_loop.py`
- `src/runtime/skills/catalog/core_context.py`
- `src/runtime/skills/catalog/core_world.py`
- `src/runtime/skills/catalog/mcp_memory_read.py`
- `src/runtime/skills/catalog/mcp_memory_write.py`
- `src/controller/runtime_services.py`
- `src/controller/worker.py`

Delete this old file after copying the new set:
- `src/runtime/tools/providers/static_provider.py`

Notes:
- This refactor removes the old static-provider assembly path.
- MCP memory tools are now exposed through the MCP provider with explicit alias/binding metadata.
- `ControllerWorker` now builds a generic `mcp_servers` map and passes that into `build_runtime_services()`.
