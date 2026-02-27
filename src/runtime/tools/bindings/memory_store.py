from __future__ import annotations

from typing import Any

from runtime.tool_loop import ToolArgs, ToolHandler
from runtime.tools.resources import ToolResources


DEFAULT_OPENMEMORY_SERVER_ID = "openmemory"


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> dict[str, Any]:
        if resources.mcp is None:
            raise RuntimeError("memory_store: ToolResources.mcp is not wired")

        content = args.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("memory_store: 'content' must be a non-empty string")
        content = content.strip()

        stype = args.get("type", "contextual")
        if stype not in ("contextual", "factual", "both"):
            raise ValueError("memory_store: 'type' must be contextual|factual|both")

        facts = args.get("facts", None)
        if facts is not None and not isinstance(facts, list):
            raise ValueError("memory_store: 'facts' must be an array")

        # OpenMemory rejects type=factual|both without at least one fact.
        # Harden: if the model requests factual/both but provides no facts, coerce to contextual.
        if stype in ("factual", "both") and (facts is None or (isinstance(facts, list) and len(facts) == 0)):
            stype = "contextual"
            facts = None

        tags = args.get("tags", None)
        if tags is not None and not isinstance(tags, list):
            raise ValueError("memory_store: 'tags' must be an array")

        metadata = args.get("metadata", None)
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("memory_store: 'metadata' must be an object")

        # Tenant/user_id is NOT LLM-controlled. Always use OpenMemory user id from config.
        user_id = (getattr(resources, "mcp_openmemory_user_id", "") or "llm_thalamus").strip() or "llm_thalamus"

        mcp_args: dict[str, Any] = {
            "content": content,
            "type": stype,
            "user_id": user_id,
        }
        if facts is not None:
            mcp_args["facts"] = facts
        if tags is not None:
            mcp_args["tags"] = tags
        if metadata is not None:
            md = dict(metadata)
            md.setdefault("source", "llm_thalamus")
            mcp_args["metadata"] = md
        else:
            mcp_args["metadata"] = {"source": "llm_thalamus"}

        res = resources.mcp.call_tool(
            DEFAULT_OPENMEMORY_SERVER_ID,
            name="openmemory_store",
            arguments=mcp_args,
            request_id=102,
        )

        ok = bool(getattr(res, "ok", True)) if not isinstance(res, dict) else bool(res.get("ok", True))
        if not ok:
            err = getattr(res, "error", None) if not isinstance(res, dict) else res.get("error")
            return {
                "ok": False,
                "error": err if isinstance(err, dict) else {"message": "openmemory_store failed"},
            }

        # NEW (success, minimal)
        return {"ok": True}

    return handler
