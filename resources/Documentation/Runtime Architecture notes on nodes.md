# llm_thalamus Runtime Architecture Notes
## Controller Nodes, Tool Loops, and Execution State

This document describes the stabilized runtime architecture of llm_thalamus following controller-loop debugging and MCP tool integration.


---

# 1. Controller Node Model

Controller nodes operate using sandwich execution mode.

Each round performs the following steps:

1. render prompt
2. model emits one action
3. runtime executes the action
4. reducer updates canonical state
5. controller evaluates termination

Pseudo-flow:

while not stop_when(state):

    prompt = render_prompt(state)

    action = llm(prompt)

    if action is tool_call:
        execute_tool()
        apply_reducer()

    else:
        repair_invalid_output()

Controller nodes do not produce final user responses.

They orchestrate tool execution until routing occurs.


---

# 2. Canonical vs Historical State

The prompt contains two categories of information.


## Canonical State

Authoritative system state:

WORLD_JSON  
CONTEXT_JSON

Reducers update this state.

This state represents the current truth.


## Historical Evidence

Execution history is stored in:

TOOL_TRANSCRIPT

Transcript entries include:

- step
- tool name
- tool kind
- arguments
- result
- status

Transcript entries are evidence only, not authoritative state.


---

# 3. Execution State Block

To solve implicit control-flow problems, an explicit execution state block was added.

Example:

EXECUTION_STATE

NODE_RUN: llm.context_builder  
CURRENT_ROUND: 3

LAST_ACTION  
  NAME: openmemory_query  
  KIND: mcp  
  STATUS: ok

PROGRESS  
  TOOL_TRANSCRIPT is history  
  WORLD and CONTEXT are canonical state

NEXT_ACTION  
  do not repeat previous tool unless required  
  emit exactly one action

This allows the LLM to reason about progress directly.


---

# 4. Tool Execution Pipeline

Tool calls follow this pipeline:

LLM tool call  
↓  
chat_stream()  
↓  
tool handler  
↓  
reducer  
↓  
state mutation  
↓  
controller evaluation

Reducers are responsible for updating canonical state.

Examples:

- _apply_route_from_tool
- context_apply_ops
- world_apply_ops


---

# 5. Routing System

Routing is performed through the route_node tool.

Reducers write routing signals into runtime state:

runtime.context_builder_route_node  
runtime.context_builder_route_applied

Graph routing logic reads this state:

context_next_selector()

The graph transitions after the controller node returns.


---

# 6. Node-Specific Tool Schema

Tool schemas are specialized per node.

Example:

context_builder.route_node.node.enum = ["answer"]

The model only sees valid route targets.

Invalid route targets now produce:

ok: false  
error: invalid_route_target


---

# 7. Terminal Tool Latch

A terminal latch ensures that controller nodes terminate immediately when a terminal tool condition occurs.

if terminal_tool_triggered:
    return state

This prevents extra controller rounds.


---

# 8. Model Role: Controller, Not Assistant

Controller nodes should behave like deterministic workflow engines.

They must:

- emit exactly one action
- avoid conversational responses
- operate on canonical state
- use tool calls to perform work

Prompt design should reinforce this role.


---

# 9. Current System Properties

The runtime now guarantees:

- deterministic tool execution
- explicit tool failure semantics
- stable routing behaviour
- controller step awareness
- canonical state integrity

Future work primarily involves:

- prompt tightening
- code cleanup
- removal of legacy logic
- improved tool schemas
