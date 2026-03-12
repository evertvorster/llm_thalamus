from __future__ import annotations
from typing import Callable
from runtime.deps import Deps
from runtime.registry import NodeSpec, register
from runtime.services import RuntimeServices
from runtime.state import State
from runtime.nodes_common import run_structured_node  # or run_streaming_answer_node / run_controller_node

# ============================================================================
# Node Metadata (REQUIRED)
# ============================================================================
# Conventions:
# - NODE_ID: Unique identifier, should match graph node key
# - GROUP: Logical grouping (e.g., "llm", "tool", "system")
# - LABEL: Human-readable name for UI/logging
# - PROMPT_NAME: Must exist under resources/prompts/<PROMPT_NAME>.txt
# - ROLE_KEY: Must exist in cfg.llm.roles (deps.get_llm(ROLE_KEY) must succeed)

NODE_ID = "llm.<node_name>"
GROUP = "llm"
LABEL = "<Human Readable Name>"
PROMPT_NAME = "runtime_<node_name>"  # resources/prompts/runtime_<node_name>.txt
ROLE_KEY = "<role_key>"  # e.g., "router", "answer", "planner", "reflect"

# ============================================================================
# Node Implementation
# ============================================================================

def make(deps: Deps, services: RuntimeServices) -> Callable[[State], State]:
    """
    Factory function that returns the node callable.
    
    Args:
        deps: Runtime dependencies (provider, prompts, roles)
        services: Runtime services (tools, resources)
    
    Returns:
        Callable[[State], State]: The node function
    """

    # ------------------------------------------------------------------------
    # Apply Result (REQUIRED for structured nodes)
    # ------------------------------------------------------------------------
    # Mutates state based on LLM output. Keep this pure and focused.
    def apply_result(state: State, obj: dict) -> None:
        """
        Apply the LLM's structured output to state.
        
        Args:
            state: The runtime state dict (mutated in-place)
            obj: Parsed JSON object from LLM response
        """
        # Example:
        # value = obj.get("some_key")
        # if isinstance(value, str):
        #     state.setdefault("task", {})["some_key"] = value
        pass

    # ------------------------------------------------------------------------
    # Node Function (REQUIRED)
    # ------------------------------------------------------------------------
    def node(state: State) -> State:
        """
        Execute the node's logic.
        
        Token Resolution:
        - Tokens are resolved AUTOMATICALLY by TokenBuilder
        - TokenBuilder reads prompt, extracts <<TOKEN>> placeholders
        - Resolves against GLOBAL_TOKEN_SPEC in nodes_common.py
        - No manual token dict construction needed
        
        Args:
            state: The runtime state dict
        
        Returns:
            State: The modified state dict
        """
        # TokenBuilder handles prompt rendering automatically via GLOBAL_TOKEN_SPEC
        # No manual tokens = {...} construction needed
        return run_structured_node(
            state=state,
            deps=deps,
            services=services,
            node_id=NODE_ID,
            label=LABEL,
            role_key=ROLE_KEY,
            prompt_name=PROMPT_NAME,
            # tokens=...,  ← REMOVED (TokenBuilder handles it)
            node_key_for_tools=None,  # Set if this node uses tools
            apply_result=apply_result,
        )

    return node

# ============================================================================
# Registration (REQUIRED)
# ============================================================================

register(NodeSpec(
    node_id=NODE_ID,
    group=GROUP,
    label=LABEL,
    role=ROLE_KEY,
    make=make,
    prompt_name=PROMPT_NAME,
))