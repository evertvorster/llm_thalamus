# Ponytail Simplification Audit

*Generated 2026-06-20 by scout subagent*

---

## High-Impact (large simplification, low risk)

### H1. definitions/ + bindings/ split → merge each tool into one file

**Files:** `src/runtime/tools/definitions/{read,write,edit,bash,chat_history_tail,world_apply_ops}.py` (6 files, ~18 lines each) + `src/runtime/tools/bindings/{read,write,edit,bash,chat_history_tail,world_apply_ops}.py` (6 files, ~20-60 lines each)

**What's wrong:** Every tool is split into two files: a `definitions/<tool>.py` that exports `tool_def() -> ToolDef` and a `bindings/<tool>.py` that exports `bind(resources) -> ToolHandler`. They are **always used together** — you never deploy a definition without its binding or vice versa. The split adds 6 extra files and 6 extra import lines for zero benefit.

**Proposal:** Merge each pair into a single file at `src/runtime/tools/local/<tool>.py` exporting both `tool_def` and `bind`. This eliminates:
- 6 files
- 6 import statements in `local_provider.py`
- The `definitions/` and `bindings/` directories entirely

**Before (2 files per tool):**
```python
# definitions/read.py
def tool_def() -> ToolDef:
    return ToolDef(name="read", ...)

# bindings/read.py
def bind(resources) -> ToolHandler:
    def handler(args): ...
    return handler
```

**After (1 file per tool):**
```python
# local/read.py
def tool_def() -> ToolDef:
    return ToolDef(name="read", ...)

def bind(resources) -> ToolHandler:
    ...
```

The 6 definitions that have no binding (they're all paired) means this is a clean merge. `local_provider.py` would import from `runtime.tools.local.bash` instead of `runtime.tools.definitions.bash` and `runtime.tools.bindings.bash`.

---

### H2. skills/catalog/ directory: 5 files → 1 file

**Files:** `src/runtime/skills/catalog/*.py` (5 files, ~4-7 lines each)

**What's wrong:** Each skill is a separate file with exactly 2 exports: `SKILL_NAME` (a string) and `TOOL_SELECTORS` (a tuple of `ToolSelector`). Every file follows the exact same 4-line pattern. The catalog is already registered in `ENABLED_SKILLS` (a set of strings) and the selection logic is entirely driven by the `ToolSelector` objects.

**Proposal:** Replace with a single `src/runtime/skills/catalog.py` containing all 5 skills in a dict. This eliminates 4 files and makes it easy to see all skills at a glance.

**Simplified:**
```python
# catalog.py
SKILLS = {
    "core_context": (ToolSelector(public_name="chat_history_tail"),),
    "core_files": (ToolSelector(public_name="read"), ToolSelector(public_name="write"),
                   ToolSelector(public_name="edit"), ToolSelector(public_name="bash")),
    "core_world": (ToolSelector(public_name="world_apply_ops"),),
    "mcp_mempalace_full": (ToolSelector(kind="mcp", server_id="mempalace"),),
    "mcp_mempalace_write": (ToolSelector(kind="mcp", server_id="mempalace", remote_name="mempalace_add_drawer"),),
}
```

Then `toolkit.py`'s `_load_skills()` becomes:
```python
def _load_skills():
    return {name: Skill(name=name, selectors=selectors) for name, selectors in SKILLS.items()}
```

---

### H3. Duplicate ToolProvider definition (dead code in descriptor.py)

**Files:**
- `src/runtime/tools/descriptor.py` lines 57-60 (unused `ToolProvider` Protocol)
- `src/runtime/tools/providers/base.py` lines 4-6 (the one actually used)

**What's wrong:** `ToolProvider` is defined twice — once as a `Protocol` in `descriptor.py` and once as a plain class in `providers/base.py`. The `descriptor.py` version is **never imported anywhere** (confirmed via grep). It's a dead interface definition.

**Proposal:** Remove the dead `ToolProvider` Protocol from `descriptor.py` (lines 57-60). The `providers/base.py` version is the canonical one. Only the `base.py` version is extended by `LocalToolProvider` and `MCPToolProvider`.

---

### H4. `RoleLLM.generate_stream()` — dead wrapper

**File:** `src/runtime/deps.py` lines 22-44

**What's wrong:** `RoleLLM` has a `generate_stream()` method that wraps `provider.chat_stream()` by constructing a single-user-message `ChatRequest`. But **nothing calls it** — the actual tool loop (`tool_loop.py`/`loop.py`) builds `ChatRequest` directly with full multi-message histories. The whole `RoleLLM` class may be vestigial (it's only used as a type annotation for `get_llm()` in `Deps`).

**Proposal:** Remove `generate_stream()` (15 lines). If `RoleLLM` is only used for type annotations, it could become a simple dataclass without behavior — or inlined into `Deps`.

---

### H5. `LLMProvider` ABC → Protocol (single-implementation ABC)

**File:** `src/runtime/providers/base.py` (100+ lines)

**What's wrong:** `LLMProvider` is an abstract base class with 5 `@abstractmethod` methods and 5 optional methods. With only 2 concrete implementations (`OllamaProvider` and `OpenAICompatibleProvider`), the ABC pattern adds ceremony (`raise NotImplementedError`, `@abstractmethod`, ABC metaclass) for minimal value. The optional methods (`ping`, `diagnostics`, `capabilities`, `build_chat_payload`, `build_chat_curl`) have default implementations that just `return` — they'd work identically as Protocol methods.

**Proposal:** Convert to `Protocol`, removing `ABC` import, `@abstractmethod` decorators, and `NotImplementedError` bodies. This is low-risk since all callers use duck typing via the `Deps` wrapper anyway.

---

## Medium-Impact (worthwhile but smaller win)

### M1. `parse_first_json_object` — trivial wrapper

**Files:** `src/runtime/nodes_common/primitives.py` line 42 + `src/runtime/json_extract.py`

**What's wrong:** `primitives.parse_first_json_object()` is a 3-line function that calls `json_extract.extract_first_json_object()` and wraps the exception:

```python
def parse_first_json_object(text: str) -> dict:
    try:
        return extract_first_json_object(text)
    except Exception as e:
        raise RuntimeError("output must be a JSON object") from e
```

Called only once in `loop.py` line 332. The indirection adds cognitive overhead and a slightly worse error message.

**Proposal:** Inline the call in `loop.py` or move the `RuntimeError` wrapper into `json_extract.py` itself. Eliminate the wrapper function.

---

### M2. Duplicate `_TOKEN_RE` regex

**Files:**
- `src/runtime/prompting.py` line 8
- `src/runtime/nodes_common/context.py` line 14

**What's wrong:** Both files define `_TOKEN_RE = re.compile(r"<<([A-Z0-9_]+)>>")` independently. Same pattern, same purpose (finding `<<TOKEN>>` placeholders).

**Proposal:** Export `TOKEN_RE` from `prompting.py` and import it in `context.py`. One regex, one canonical source.

---

### M3. Probe/experiment test files — 827 lines of dead code

**Files:** `src/tests/langchain_probe_*.py`, `langgraph_test_ollama_router*.py`, `ollama_chat_interactive.py`, `chat_history_smoketest.py`, `probe_toolcall*.json`

**Lines:** ~827 lines across 9 files (all in `src/tests/`)

**What's wrong:** These are interactive experiments, not tests. `ollama_chat_interactive.py` is a REPL. `langchain_probe_*.py` were experiments with LangChain features (template, parser, splitter) that were either rejected or integrated differently. `probe_toolcall*.json` are static JSON fixtures with no test that uses them. `chat_history_smoketest.py` runs directly (not via pytest).

**Proposal:** Delete them. If any probe result is important, convert it to a real unit test first. These are not test files — they're session artifacts.

---

### M4. `runtime/tools/registry.py` — `build_default_toolset()` unused dead code

**File:** `src/runtime/tools/registry.py` (57 lines)

**What's wrong:** This module defines `build_default_toolset()` which creates a `ToolSet` with an "echo" tool. Grep confirms it is never imported or called outside this file. It was for "capability testing / spike nodes" but no spike node currently uses it.

**Proposal:** Delete the file. If needed later, recreate from git history.

---

### M5. String-based node lookup in graph_build.py adds indirection without benefit

**File:** `src/runtime/graph_build.py` lines 14-16

**What's wrong:** Each node is already imported by name in `nodes/__init__.py` (for side-effect registration). Then `graph_build.py` looks them up by string key via `get("context.bootstrap")`. The string key is the same as the node_id defined in the node file. This string indirection adds a lookup step and a possible `KeyError` runtime path that can't happen if you just import the function directly.

**Proposal:** Replace string lookup with direct function import:
```python
from runtime.nodes.context_bootstrap import context_bootstrap_node
g.add_node("context_bootstrap", context_bootstrap_node)
```
Or keep the registry but inline the keys to remove the indirection. Either way eliminates a failure mode.

---

## Low-Impact / Debatable (technically simpler but may have good reasons)

### L1. `State = dict[str, Any]` — TypedDicts exist but aren't enforced

**File:** `src/runtime/state.py`

**Observation:** `RuntimeTask`, `RuntimeFinal`, `RuntimeRuntime`, and `RuntimeState` TypedDicts exist as documentation, but `State = dict[str, Any]` is the runtime type. The TypedDicts provide IDE hints but aren't checked anywhere. This is a minor documentation-vs-reality gap, not a simplification opportunity per se — removing them would lose documentation value.

**Recommendation:** Keep as-is. The TypedDicts are lightweight documentation that costs nothing.

---

### L2. `TurnEventFactory` → ~20 factory methods

**File:** `src/runtime/events.py` (369 lines total, factory is the bulk)

**Observation:** `TurnEventFactory` has one factory method per event type (turn_start, node_start, tool_call, etc.), each ~10-15 lines. A `make()` + dictionary approach could reduce to ~50 lines total. But the current structure catches payload structure errors at definition time and is already stable.

**Recommendation:** Leave alone. The factory methods are well-documented and used everywhere. The risk of introducing bugs outweighs the line-count win.

---

### L3. `OllamaProvider` and `OpenAICompatibleProvider` duplicate message/tool schema conversion

**Observation:** Both providers convert `Message`/`ToolCall`/`ToolDef` to provider-specific wire formats. The schemas are OpenAI-compatible in both cases, so ~80% of the conversion code is identical. Could extract shared `_to_wire()` helpers.

**Recommendation:** Low priority — the duplication is explicit and easy to maintain independently. Only worth consolidating if adding a third provider.

---

### L4. `Deps` vs `RuntimeServices` split — two DI bundles

**Observation:** `Deps` (provider + roles + prompts) and `RuntimeServices` (tools + resources) are separate frozen dataclasses passed into every node factory. The split is intentional — providers are "what you think with" and tools are "what you touch" — but every single node factory receives both and destructures them.

**Recommendation:** Keep the split. It's a clear architectural boundary. Both objects are small (2-3 fields each) and the separation provides useful compile-time isolation.

---

### L5. LangGraph dependency for a 3-node linear graph

**Observation:** The entire graph is 3 nodes in a straight line: `bootstrap → primary_agent → reflect_memory → END`. LangGraph resolves this to... execute the nodes in order. The runtime (`langgraph_runner.py`) adds threading and event streaming on top. Approximately 85 lines of LangGraph code (`graph_build.py` + imports) plus the full `langgraph` dependency for what could be:

```python
state = bootstrap(state)
state = primary_agent(state)
state = reflect_memory(state)
```

**Recommendation:** Debatable. LangGraph provides the node lifecycle, state management, and potential for future branching/conditional graphs. If no conditional routing or parallel execution is planned, this is a clear simplification target. If future architecture plans include complex routing, keep it.

---

## Already Minimal (areas that pass the ladder — worth noting so we don't touch them)

### AM1. Tool binding implementations (read, write, edit, bash, etc.)
Each binding is a clean ~20-60 line function factory. No abstraction, no base class, no over-engineering. The `_fs_common.py` shared utility is appropriately factored.

### AM2. `context_bootstrap.py` node
Mechanical, side-effect-focused, no LLM call. Clean separation of prefilling from reasoning.

### AM3. `llm_reflect_memory.py` node
Short (~140 lines), focused, does exactly one thing (write to MemPalace). Good.

### AM4. `EventBus`
Minimalist thread-safe queue with two iteration modes. 100 lines including docstrings. Can't get much simpler.

### AM5. `prompting.py`
One function (`render_tokens`) with regex replacement. 15 lines. Perfect.

### AM6. `graph_policy.py`
One function (`route_after_router`) that returns a string. 7 lines. Trivially minimal.

---

## Summary of Actions (ranked by impact)

| Priority | Issue | Files deleted | Lines removed |
|----------|-------|---------------|---------------|
| H1 | Merge definitions + bindings | 6 | ~80 |
| H2 | Flatten skills catalog | 4 | ~20 |
| H3 | Remove dead ToolProvider protocol | 0 | 3 |
| H4 | Remove dead `generate_stream` | 0 | 15 |
| H5 | ABC → Protocol for LLMProvider | 0 | ~10 |
| M1 | Inline parse_first_json_object | 0 | 3 |
| M2 | Deduplicate TOKEN_RE | 0 | 2 |
| M3 | Delete probe/experiment files | 9 | 827 |
| M4 | Delete dead build_default_toolset | 1 | 57 |
| M5 | Direct imports in graph_build | 0 | ~5 |

**Total: ~20 files deleted, ~1000+ lines removed** without losing any functionality.
