#!/usr/bin/env python3
"""Simple tool registry for llm_thalamus.

This keeps knowledge of available tools (names, metadata) outside of the
Thalamus core so that we can grow the toolset without bloating the router.

Right now we only support a single internal tool:

- ``memory.retrieve`` – retrieve relevant memories from the MemoryModule.

The registry interface is intentionally minimal:

- ``discover(name)``  -> JSON string describing tools
- ``execute(session_id, name, args)`` -> JSON string with tool result
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


class ToolRegistry:
    """Registry + dispatcher for LLM-callable tools."""

    def __init__(
        self,
        tools_config: Optional[Dict[str, Any]] = None,
        memory_module: Any = None,
    ) -> None:
        # Raw config coming from config.json["tools"]
        self.tools_config: Dict[str, Any] = tools_config or {}
        # Optional dependency on the in-process MemoryModule
        self.memory = memory_module

    # ------------------------------------------------------------------ discovery

    def discover(self, tool_name: str) -> str:
        """Return metadata about tools as a JSON string.

        - ``tool_name == "all"`` returns the entire tools config.
        - Otherwise we return metadata for just that tool, or an error.
        """
        if tool_name == "all":
            return json.dumps(self.tools_config, indent=2, sort_keys=True)

        meta = self.tools_config.get(tool_name)
        if not meta:
            return json.dumps(
                {"error": f"Unknown tool {tool_name!r}"},
                indent=2,
                sort_keys=True,
            )
        return json.dumps({tool_name: meta}, indent=2, sort_keys=True)

    # ------------------------------------------------------------------ execution

    def execute(self, session_id: str, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return its result as JSON.

        ``args`` is a dict coming from the LLM's tool_call message.
        """
        if not tool_name:
            return json.dumps(
                {"ok": False, "error": "Missing tool name in tool_call."}
            )

        meta = self.tools_config.get(tool_name, {})
        kind = meta.get("kind")

        # For now we special-case the built-in memory tool, but the config
        # still documents it for the LLM.
        if tool_name == "memory.retrieve" or kind == "internal_memory":
            return self._execute_memory_retrieve(args)

        return json.dumps(
            {
                "ok": False,
                "error": f"Unsupported or unknown tool {tool_name!r}",
            }
        )

    # ------------------------------------------------------------------ individual tools

    def _execute_memory_retrieve(self, args: Dict[str, Any]) -> str:
        """Bridge to the in-process MemoryModule.retrieve_relevant_memories()."""
        if self.memory is None:
            return json.dumps(
                {"ok": False, "error": "Memory module not available in ToolRegistry."}
            )

        query = (args or {}).get("query", "")
        if not isinstance(query, str) or not query.strip():
            return json.dumps(
                {
                    "ok": False,
                    "error": "Argument 'query' (non-empty string) is required.",
                }
            )

        # Optional: allow the tool to override k, otherwise we use the module default.
        k = args.get("k")
        # The current MemoryModule API doesn't accept k, so we ignore it for now.

        memories_block = self.memory.retrieve_relevant_memories(query)
        return json.dumps(
            {
                "ok": True,
                "query": query,
                "k": k,
                "memories": memories_block or "",
            }
        )
