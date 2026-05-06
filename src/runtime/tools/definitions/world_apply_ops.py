from __future__ import annotations

from runtime.providers.types import ToolDef


def tool_def() -> ToolDef:
    return ToolDef(
        name="world_apply_ops",
        description=(
            "Apply validated modifications to the persistent world state. "
            "Supports set, add, and remove operations on allowlisted paths. "
            "Valid set paths: /project, /user/location, /identity/user_location, "
            "/identity/user_name, /identity/agent_name, /rules, /goals, /topics. "
            "Use /identity/user_location for the user's actual location stored in identity. "
            "Use /project to replace the project value; do not use /project/name or /project/title. "
            "The /project value must be a plain string, e.g. "
            "{\"op\":\"set\",\"path\":\"/project\",\"value\":\"llm_thalamus\"}; "
            "do not wrap it as {\"name\": ...}. "
            "Valid add/remove list paths: /rules, /goals, /topics."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["set", "add", "remove"],
                            },
                            "path": {
                                "type": "string",
                                "enum": [
                                    "/project",
                                    "/user/location",
                                    "/identity/user_location",
                                    "/identity/user_name",
                                    "/identity/agent_name",
                                    "/rules",
                                    "/goals",
                                    "/topics",
                                ],
                                "description": (
                                    "Allowlisted JSON pointer path. Use /identity/user_location "
                                    "for the user's actual location stored in identity. Use /project "
                                    "for project updates; /project/name and /project/title are invalid. "
                                    "When path is /project, value must be a plain string like "
                                    "llm_thalamus, not an object like {name: llm_thalamus}. "
                                    "Only /rules, /goals, and /topics support add/remove."
                                ),
                            },
                            "value": {
                                "description": (
                                    "New value for set, or item(s) for add/remove. For /project, "
                                    "pass a plain string, e.g. \"llm_thalamus\", never an object."
                                )
                            }
                        },
                        "required": ["op", "path"],
                    },
                }
            },
            "required": ["ops"],
        },
    )
