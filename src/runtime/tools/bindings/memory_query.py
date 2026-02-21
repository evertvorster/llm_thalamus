from __future__ import annotations

import json
from typing import Any

from runtime.tool_loop import ToolHandler
from runtime.tools.resources import ToolResources


DEFAULT_OPENMEMORY_SERVER_ID = "openmemory"


def _as_dict(x: Any) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _extract_items_from_mcp_result(mcp_result: Any) -> list[dict[str, Any]]:
    content = getattr(mcp_result, "content", None)
    if content is None and isinstance(mcp_result, dict):
        content = mcp_result.get("content")

    if not isinstance(content, list):
        return []

    json_texts: list[str] = []
    for c in content:
        if not isinstance(c, dict):
            continue
        if c.get("type") != "text":
            continue
        t = c.get("text")
        if isinstance(t, str):
            s = t.strip()
            if s.startswith("{") and s.endswith("}"):
                json_texts.append(s)

    for s in json_texts:
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            items = obj.get("items")
            if isinstance(items, list):
                out: list[dict[str, Any]] = []
                for it in items:
                    if isinstance(it, dict):
                        out.append(it)
                return out
    return []


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args_json: str) -> str:
        if resources.mcp is None:
            raise RuntimeError("memory_query: ToolResources.mcp is not wired")

        try:
            args = json.loads(args_json)
        except Exception as e:
            raise ValueError(f"memory_query: invalid JSON args: {e}") from e
        if not isinstance(args, dict):
            raise ValueError("memory_query: args must be an object")

        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("memory_query: 'query' must be a non-empty string")
        query = query.strip()

        qtype = args.get("type", "contextual")
        if qtype not in ("contextual", "factual", "unified"):
            raise ValueError("memory_query: 'type' must be contextual|factual|unified")

        k = args.get("k", 5)
        try:
            k = int(k)
        except Exception:
            raise ValueError("memory_query: 'k' must be an integer")
        if k < 1 or k > 16:
            raise ValueError("memory_query: 'k' must be in [1, 16]")

        sector = args.get("sector", None)
        if sector is not None:
            if sector not in ("episodic", "semantic", "procedural", "emotional", "reflective"):
                raise ValueError("memory_query: invalid 'sector'")

        min_salience = args.get("min_salience", None)
        if min_salience is not None:
            try:
                min_salience = float(min_salience)
            except Exception:
                raise ValueError("memory_query: 'min_salience' must be a number")
            if min_salience < 0.0 or min_salience > 1.0:
                raise ValueError("memory_query: 'min_salience' must be in [0, 1]")

        at = args.get("at", None)
        if at is not None and not isinstance(at, str):
            raise ValueError("memory_query: 'at' must be a string")

        fact_pattern = args.get("fact_pattern", None)
        if fact_pattern is not None and not isinstance(fact_pattern, dict):
            raise ValueError("memory_query: 'fact_pattern' must be an object")

        user_id = args.get("user_id", None)
        if user_id is not None:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("memory_query: 'user_id' must be a non-empty string")
            user_id = user_id.strip()
        else:
            user_id = (resources.mcp_default_user_id or "llm_thalamus").strip() or "llm_thalamus"

        mcp_args: dict[str, Any] = {
            "query": query,
            "type": qtype,
            "k": k,
            "user_id": user_id,
        }
        if sector is not None:
            mcp_args["sector"] = sector
        if min_salience is not None:
            mcp_args["min_salience"] = min_salience
        if at is not None:
            mcp_args["at"] = at
        if fact_pattern is not None:
            mcp_args["fact_pattern"] = fact_pattern

        res = resources.mcp.call_tool(
            DEFAULT_OPENMEMORY_SERVER_ID,
            name="openmemory_query",
            arguments=mcp_args,
            request_id=101,
        )

        ok = bool(getattr(res, "ok", True)) if not isinstance(res, dict) else bool(res.get("ok", True))
        if not ok:
            err = getattr(res, "error", None) if not isinstance(res, dict) else res.get("error")
            return json.dumps(
                {
                    "ok": False,
                    "error": _as_dict(err) or {"message": "openmemory_query failed"},
                    "items": [],
                },
                ensure_ascii=False,
            )

        items = _extract_items_from_mcp_result(res)
        return json.dumps(
            {
                "ok": True,
                "items": items,
                "returned": len(items),
                "k": k,
                "user_id": user_id,
                "note": "Do not use 'score' for ranking; rely on order + salience.",
            },
            ensure_ascii=False,
        )

    return handler