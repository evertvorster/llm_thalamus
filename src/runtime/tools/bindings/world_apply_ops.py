from __future__ import annotations

import json
from typing import Any

from controller.world_state import load_world_state
from runtime.tools.resources import ToolResources


ALLOWED_PATHS = {
    "/project",
    "/identity/user_location",
    "/identity/user_name",
    "/identity/agent_name",
    "/rules",
    "/goals",
}


def bind(resources: ToolResources):
    def handler(args_json: str) -> str:
        # Guard: world_state_path must be configured for world mutation tools.
        if getattr(resources, "world_state_path", None) is None:
            raise RuntimeError(
                "world_apply_ops: world_state_path is not set in ToolResources. "
                "Ensure build_runtime_services(...) passes world_state_path."
            )

        args = json.loads(args_json)
        ops = args.get("ops", [])

        world = load_world_state(
            path=resources.world_state_path,
            now_iso=resources.now_iso,
            tz=resources.tz,
        )

        for op in ops:
            _apply_op(world, op)

        return json.dumps(
            {
                "ok": True,
                "world": world,
            },
            ensure_ascii=False,
        )

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
        if value not in lst:
            lst.append(value)

    elif operation == "remove":
        lst = _get_path(world, path)
        if not isinstance(lst, list):
            raise RuntimeError(f"Path is not a list: {path}")
        value = op.get("value")
        if value in lst:
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
    raise RuntimeError(f"Unsupported list path: {path}")
