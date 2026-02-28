# Audit Appendix

## A1) “Unknown from snapshot” checklist

Items that cannot be confirmed from the provided zip alone:

- Packaging/distribution metadata (no `pyproject.toml`, `setup.cfg`, etc. in snapshot): how the app is installed and invoked in “installed mode” is **unknown from snapshot**.
- External service contracts:
  - OpenMemory MCP server tool schema details beyond what bindings parse.
  - Ollama model capability matrix and exact response formats (depends on installed models / server version).
- Multi-process expectations (file locking/concurrency): the code does not establish whether multiple app instances are supported.

What would confirm:
- Packaging files (`pyproject.toml`, distro PKGBUILD, etc.)
- MCP server documentation or the `tools/list` output captured for the target server(s)
- A design note on concurrency expectations for `var/` files

## A2) Supporting excerpts (≤10 lines each)

### A2.1 Prompt token enforcement (hard-fail on leftovers)

File: `src/runtime/prompting.py` (F060)

```python
from __future__ import annotations

import re
from typing import Mapping


_TOKEN_RE = re.compile(r"<<[A-Z0-9_]+>>")


def render_tokens(template: str, mapping: Mapping[str, str]) -> str:
```

### A2.2 Tool loop: tool rounds vs final formatting pass

File: `src/runtime/tool_loop.py` (F074)

```python
            obj = obj2
        except Exception:
            pass

    return obj

def _normalize_tool_result(result: ToolResult) -> str:
    """Normalize a tool handler return value into a string for tool message injection.

    - If the handler returns a string, it is passed through (assumed already formatted).
```

### A2.3 Graph wiring (entry, conditional routes)

File: `src/runtime/graph_build.py` (F045)

```python
from __future__ import annotations

from langgraph.graph import END, StateGraph

from runtime.state import State
from runtime.registry import get
from runtime.nodes import llm_router  # noqa: F401
from runtime.nodes import llm_context_builder  # noqa: F401
from runtime.nodes import llm_world_modifier  # noqa: F401
from runtime.nodes import llm_answer  # noqa: F401
```

## A3) Cross-check: snapshot already contains prior audit docs

The snapshot includes `resources/Documentation/audit_overview.md`, `audit_file_inventory.md`, and `audit_appendix.md`. This audit is newly generated for the provided zip and may differ from those shipped documents.
