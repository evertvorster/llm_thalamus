# llm_thalamus Controller Node Design Rules

This document captures the architectural lessons learned while stabilizing the llm_thalamus runtime controller loop.

It defines the design rules that future controller nodes must follow to ensure predictable behaviour and avoid the failure modes encountered during development.

The goal is to make controller nodes behave as deterministic workflow engines rather than conversational agents.


---

# 1. Controller Nodes Are Workflow Engines

Controller nodes do not behave like assistants.

Their purpose is to orchestrate tools and mutate system state until a routing decision is made.

A controller node must:

- emit exactly one action per round
- operate entirely through tool calls
- terminate through routing or a terminal tool
- avoid producing conversational text

Controller nodes are responsible for workflow progression, not user interaction.


---

# 2. Canonical State vs Historical Evidence

All controller prompts must clearly distinguish between:

Canonical state and historical evidence.


## Canonical State

Canonical state represents the authoritative current state of the system.

Examples:

WORLD_JSON  
CONTEXT_JSON

Reducers update canonical state after tool execution.

Canonical state is the source of truth.


## Historical Evidence

Historical information is provided only as supporting evidence.

Examples:

TOOL_TRANSCRIPT  
chat history  
memory search results

Historical data must never override canonical state.

Prompts must explicitly instruct the model that transcripts and history are evidence only.


---

# 3. Explicit Execution State Is Required

Controller prompts must include an explicit execution state block.

This block provides the model with the minimum information required to understand progress.

Recommended fields:

EXECUTION_STATE

NODE_RUN  
CURRENT_ROUND  

LAST_ACTION  
  NAME  
  KIND  
  STATUS  

PROGRESS  
  transcript is execution history  
  WORLD and CONTEXT are canonical state  

NEXT_ACTION_RULES


Without explicit execution state, models tend to restart reasoning from the beginning each round.


---

# 4. Each Round Must Produce Exactly One Action

Controller nodes operate under a strict contract:

Each LLM response must contain exactly one action.

Allowed actions:

- a single tool call
- a routing call
- a terminal controller tool

No natural language output is allowed.

If the model produces invalid output, the runtime must reject the output and retry.


---

# 5. Terminal Actions Must Be Explicit

Controller termination must occur through explicit terminal conditions.

Examples:

route_node  
reflect_complete  

A terminal tool must guarantee that:

- the controller loop exits immediately
- the graph transition can occur safely

The runtime must implement a **terminal latch** so the controller stops immediately after a terminal condition.


---

# 6. Tool Success Must Match System Semantics

A critical design rule is that tool success must align with runtime behaviour.

A tool must not return success unless the operation actually succeeded.

Failure example from earlier development:

route_node returned ok:true for invalid route targets.

This caused the controller to believe routing succeeded while the graph rejected it.

Tools must therefore validate inputs and return explicit failure when constraints are violated.


---

# 7. Tool Schemas Should Be Node-Specific

Tools exposed to the model should be specialized for the node that uses them.

Example:

context_builder can only route to:

answer

Therefore the route_node schema should expose:

node.enum = ["answer"]

Restricting schemas improves model reliability and prevents invalid actions.


---

# 8. Reducers Must Update Canonical State

Reducers are responsible for mutating canonical system state after tool execution.

Reducers must:

- update canonical state deterministically
- avoid ambiguous state transitions
- ensure the prompt reflects the new state on the next round

If canonical state is not updated correctly, the model may repeat actions.


---

# 9. Routing Is the Only Way to Leave a Controller Node

Controller nodes should not directly produce final output.

Instead they must route control to the next node in the graph.

Routing must be:

- explicit
- deterministic
- validated

Routing information is written to runtime state and then interpreted by the graph selector.


---

# 10. Controller Prompts Must Suppress Assistant Behaviour

Prompts must clearly state that the node is not a conversational assistant.

Important instructions include:

- do not speak to the user
- do not explain reasoning
- do not produce natural language output
- emit tool calls only

Without these constraints, the model may attempt to answer conversationally instead of executing workflow steps.


---

# 11. Runtime Must Provide Output Repair

Even with good prompts, models occasionally produce invalid outputs.

The runtime controller must therefore implement repair behaviour:

- reject invalid outputs
- provide corrective feedback
- retry the round

This ensures that transient model mistakes do not break execution.


---

# 12. Prefer Explicit State Over Implicit Reasoning

A recurring lesson from the stabilization process is that models perform better when important state is explicit.

Whenever possible:

- expose state fields directly
- avoid forcing the model to infer control flow from transcripts
- prefer structured execution state blocks


---

# 13. Controller Node Checklist

Before introducing a new controller node, verify the following:

Execution state block exists  
Tool schemas are node-specific  
Canonical vs historical state is clearly defined  
Reducers update canonical state correctly  
Terminal conditions are explicit  
Routing targets are validated  
Prompt suppresses assistant behaviour  
Runtime output repair is enabled  


---

# 14. Architectural Outcome

Following these rules ensures that controller nodes:

- behave deterministically
- avoid infinite tool loops
- maintain state consistency
- interact safely with MCP tools
- transition cleanly between graph nodes

These rules form the foundation for building additional nodes such as planners, execution nodes, and reflective maintenance nodes within the llm_thalamus architecture.
