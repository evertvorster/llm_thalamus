from __future__ import annotations

import json
from typing import Any

from controller.world_state import load_world_state
from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


ALLOWED_PATHS = {
    "/project",
    "/identity/user_location",
    "/identity/user_name",
    "/identity/agent_name",
    "/rules",
    "/goals",
    "/topics",
}


def bind(resources: ToolResources) -> ToolHandler:
    def handler(args: ToolArgs) -> ToolResult:
        # Guard: world_state_path must be configured for world mutation tools.
        if getattr(resources, "world_state_path", None) is None:
            raise RuntimeError(
                "world_apply_ops: world_state_path is not set in ToolResources. "
                "Ensure build_runtime_services(...) passes world_state_path."
            )

        if not isinstance(args, dict):
            raise ValueError("world_apply_ops: args must be an object")
        ops = args.get("ops", [])
        if isinstance(ops, str):
            try:
                ops = json.loads(ops)
            except Exception as e:
                raise ValueError(f"world_apply_ops: 'ops' string was not valid JSON: {e}") from e
        if not isinstance(ops, list):
            raise ValueError("world_apply_ops: 'ops' must be an array")

        world = load_world_state(
            path=resources.world_state_path,
            now_iso=resources.now_iso,
            tz=resources.tz,
        )

        for op in ops:
            if not isinstance(op, dict):
                raise ValueError("world_apply_ops: each op must be an object")
            _apply_op(world, op)

        return {
            "ok": True,
            "world": world,
        }

    return handler


def _apply_op(world: dict[str, Any], op: dict[str, Any]) -> None:
    operation = op["op"]
    path = op["path"]

    if path not in ALLOWED_PATHS:
        raise RuntimeError(f"Modification not allowed for path: {path}")

    if operation == "set":
        _set_path(world, path, op.get("value"))

    elif operation == "add":
        lst = _get_path(world, path)
        if not isinstance(lst, list):
            raise RuntimeError(f"Path is not a list: {path}")
        value = op.get("value")
        if isinstance(value, list):
            for item in value:
                if item not in lst:
                    lst.append(item)
        elif value not in lst:
            lst.append(value)

    elif operation == "remove":
        lst = _get_path(world, path)
        if not isinstance(lst, list):
            raise RuntimeError(f"Path is not a list: {path}")
        value = op.get("value")
        if isinstance(value, list):
            for item in value:
                if item in lst:
                    lst.remove(item)
        elif value in lst:
            lst.remove(value)

    else:
        raise RuntimeError(f"Unknown operation: {operation}")


def _set_path(world: dict[str, Any], path: str, value: Any) -> None:
    if path == "/project":
        world["project"] = value
    elif path.startswith("/identity/"):
        key = path.split("/")[-1]
        world.setdefault("identity", {})[key] = value
    else:
        world[path.strip("/")] = value


def _get_path(world: dict[str, Any], path: str):
    if path == "/rules":
        return world.setdefault("rules", [])
    if path == "/goals":
        return world.setdefault("goals", [])
    if path == "/topics":
        return world.setdefault("topics", [])
    raise RuntimeError(f"Unsupported list path: {path}")
