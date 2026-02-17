# thalamus_openmemory architecture

This package integrates the OpenMemory backend into llm_thalamus.

The project goal is strict separation between:
- config/bootstrap (one-time wiring, backend selection, health checks)
- runtime memory I/O API (read/write/query/delete)
- domain logic (query shaping, sector policy, normalization)

This prevents config bleed, duplicate logic, and accidental dependency loops.

## Package layout

- `thalamus_openmemory/bootstrap/`
  - **Allowed imports:** `config.*`, `thalamus_openmemory.api.*`, and the external SDK `openmemory.*`
  - **Responsibilities:**
    - choose backend (local sqlite vs MCP/HTTP)
    - configure environment / connection parameters
    - instantiate the backend client
    - run startup self-test
    - return a client handle to llm_thalamus
  - **Forbidden:** usage by controller/runtime code (bootstrap is called only once)

- `thalamus_openmemory/api/`
  - **Allowed imports:** pure stdlib + typing + (optionally) small local helpers
  - **Responsibilities:**
    - expose the *only* functions the rest of the app uses for memory I/O
    - define stable client protocol/types
    - provide sync wrappers for async SDK calls
  - **Forbidden imports:** `config.*`, `thalamus_openmemory.bootstrap.*`

- `thalamus_openmemory/domain/` (optional, later)
  - **Allowed imports:** pure logic only
  - **Responsibilities:**
    - shaping memory queries
    - sector policies and limits
    - normalization/formatting of retrieved memories
  - **Forbidden:** any OpenMemory I/O or config.

## Naming and import rules (non-negotiable)

1. Runtime code MUST NOT import the external SDK (`openmemory.*`) directly.
2. Runtime code MUST ONLY import from `thalamus_openmemory.api`.
3. Only bootstrap may import `config`.
4. Only bootstrap may import `openmemory.client.Memory` or any other SDK entry point.

This ensures:
- a single instantiation point
- a stable runtime interface
- no accidental reconfiguration or hidden side-effects

## Public API for the rest of the application

All non-bootstrap code must use one of:

```python
from thalamus_openmemory.api import (
    add_memory,
    delete_memory,
    search_memories,
    add_memory_async,
    delete_memory_async,
    search_memories_async,
)
