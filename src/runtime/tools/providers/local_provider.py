from __future__ import annotations

from dataclasses import dataclass

from runtime.tools.descriptor import BoundTool, ToolDescriptor
from runtime.tools.types import ToolResult
from runtime.tools.providers.base import ToolProvider
from runtime.tools.resources import ToolResources

from runtime.tools.definitions import chat_history_tail as def_chat_history_tail
from runtime.tools.bindings import chat_history_tail as bind_chat_history_tail

from runtime.tools.definitions import world_apply_ops as def_world_apply_ops
from runtime.tools.bindings import world_apply_ops as bind_world_apply_ops

from runtime.tools.definitions import answer_user as def_answer_user
from runtime.tools.bindings import answer_user as bind_answer_user



def _require_object(result: ToolResult) -> dict:
    if not isinstance(result, dict):
        raise ValueError(f"tool result must be an object (got {type(result).__name__})")
    return result


def _validate_source_object(result: ToolResult) -> None:
    obj = _require_object(result)
    for k in ("ok", "records"):
        if k not in obj:
            raise ValueError(f"tool result missing key: {k}")
    if not isinstance(obj.get("ok"), bool):
        raise ValueError("tool result 'ok' must be a boolean")
    if not isinstance(obj.get("records"), list):
        raise ValueError("tool result 'records' must be a list")


def _validate_ok_object(result: ToolResult) -> None:
    obj = _require_object(result)
    ok = obj.get("ok")
    if not isinstance(ok, bool):
        raise ValueError("tool result 'ok' must be a boolean")


@dataclass(frozen=True)
class _LocalToolSpec:
    descriptor: ToolDescriptor
    binder_name: str
    validator_name: str | None = None


class LocalToolProvider(ToolProvider):
    """In-process tools backed by local bindings."""

    def __init__(self, resources: ToolResources):
        self._resources = resources

    def _approval_mode_for(self, tool_name: str) -> str:
        policy = dict(self._resources.internal_tool_policy or {})
        tool_cfg = policy.get(tool_name)
        if not isinstance(tool_cfg, dict):
            return "auto"
        approval = str(tool_cfg.get("approval") or "auto").strip() or "auto"
        if approval not in {"auto", "ask", "deny"}:
            return "auto"
        return approval

    def list_tools(self) -> list[BoundTool]:
        specs = [
            _LocalToolSpec(
                descriptor=ToolDescriptor(
                    public_name=def_chat_history_tail.tool_def().name,
                    description=def_chat_history_tail.tool_def().description,
                    parameters=def_chat_history_tail.tool_def().parameters,
                    kind="local",
                    approval_mode=self._approval_mode_for(def_chat_history_tail.tool_def().name),
                ),
                binder_name="chat_history_tail",
                validator_name="source",
            ),
            _LocalToolSpec(
                descriptor=ToolDescriptor(
                    public_name=def_world_apply_ops.tool_def().name,
                    description=def_world_apply_ops.tool_def().description,
                    parameters=def_world_apply_ops.tool_def().parameters,
                    kind="local",
                    approval_mode=self._approval_mode_for(def_world_apply_ops.tool_def().name),
                ),
                binder_name="world_apply_ops",
                validator_name="ok",
            ),
            _LocalToolSpec(
                descriptor=ToolDescriptor(
                    public_name=def_answer_user.tool_def().name,
                    description=def_answer_user.tool_def().description,
                    parameters=def_answer_user.tool_def().parameters,
                    kind="local",
                    approval_mode=self._approval_mode_for(def_answer_user.tool_def().name),
                ),
                binder_name="answer_user",
                validator_name="ok",
            ),
        ]

        validators = {
            None: None,
            "source": _validate_source_object,
            "ok": _validate_ok_object,
        }
        binders = {
            "chat_history_tail": bind_chat_history_tail.bind,
            "world_apply_ops": bind_world_apply_ops.bind,
            "answer_user": bind_answer_user.bind,
        }

        out: list[BoundTool] = []
        for spec in specs:
            out.append(
                BoundTool(
                    descriptor=spec.descriptor,
                    handler=binders[spec.binder_name](self._resources),
                    validator=validators[spec.validator_name],
                )
            )
        return out
