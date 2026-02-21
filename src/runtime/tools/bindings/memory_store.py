from __future__ import annotations

import json
from typing import Any

from runtime.tool_loop import ToolHandler
from runtime.tools.resources import ToolResources


DEFAULT_OPENMEMORY_SERVER_ID = "openmemory"
DEFAULT_USER_ID = "llm_thalamus"


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args_json: str) -> str:
        if resources.mcp is None:
            raise RuntimeError("memory_store: ToolResources.mcp is not wired")

        try:
            args = json.loads(args_json)
        except Exception as e:
            raise ValueError(f"memory_store: invalid JSON args: {e}") from e
        if not isinstance(args, dict):
            raise ValueError("memory_store: args must be an object")

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

        tags = args.get("tags", None)
        if tags is not None and not isinstance(tags, list):
            raise ValueError("memory_store: 'tags' must be an array")

        metadata = args.get("metadata", None)
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("memory_store: 'metadata' must be an object")

        user_id = args.get("user_id", None)
        if user_id is not None:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("memory_store: 'user_id' must be a non-empty string")
            user_id = user_id.strip()
        else:
            user_id = DEFAULT_USER_ID

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
            # Add minimal provenance if caller didn't set it
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
            return json.dumps(
                {
                    "ok": False,
                    "error": err if isinstance(err, dict) else {"message": "openmemory_store failed"},
                },
                ensure_ascii=False,
            )

        # We return the raw content text for debugging if present, but keep it small.
        text = getattr(res, "text", "") if not isinstance(res, dict) else str(res.get("text", "") or "")
        return json.dumps(
            {
                "ok": True,
                "stored": True,
                "user_id": user_id,
                "summary": text[:400],
            },
            ensure_ascii=False,
        )

    return handler