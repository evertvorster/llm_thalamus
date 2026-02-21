from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="memory_query",
        description=(
            "Query durable semantic/temporal memories via OpenMemory (MCP). "
            "Use for retrieving relevant background context, preferences, or facts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Free-form search text.",
                },
                "type": {
                    "type": "string",
                    "enum": ["contextual", "factual", "unified"],
                    "default": "contextual",
                    "description": (
                        "Query type: 'contextual' (semantic, default), "
                        "'factual' (temporal facts), or 'unified' (both)."
                    ),
                },
                "k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "default": 5,
                    "description": "Maximum number of results to return.",
                },
                "sector": {
                    "type": "string",
                    "enum": ["episodic", "semantic", "procedural", "emotional", "reflective"],
                    "description": "Optional: restrict to a sector (contextual/unified only).",
                },
                "min_salience": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Optional: minimum salience threshold (contextual/unified only).",
                },
                "at": {
                    "type": "string",
                    "description": "ISO timestamp for factual queries (default: now).",
                },
                "fact_pattern": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                    },
                    "additionalProperties": False,
                    "description": (
                        "Optional: fact pattern for factual/unified queries. "
                        "Omit fields for wildcard behavior."
                    ),
                },
                "user_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Optional override for multi-tenant isolation. "
                        "If omitted, llm_thalamus will inject its default user_id."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )