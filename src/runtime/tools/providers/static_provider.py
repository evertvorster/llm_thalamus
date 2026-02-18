from __future__ import annotations

from dataclasses import dataclass

from runtime.providers.types import ToolDef
from runtime.tool_loop import ToolHandler
from runtime.tools.resources import ToolResources

from runtime.tools.definitions import chat_history_tail as def_chat_history_tail
from runtime.tools.bindings import chat_history_tail as bind_chat_history_tail


@dataclass(frozen=True)
class StaticTool:
    tool_def: ToolDef
    handler: ToolHandler


class StaticProvider:
    """Static (in-process) tools backed by concrete ToolResources."""

    def __init__(self, resources: ToolResources):
        self._resources = resources

    def get(self, name: str) -> StaticTool | None:
        if name == "chat_history_tail":
            return StaticTool(
                tool_def=def_chat_history_tail.tool_def(),
                handler=bind_chat_history_tail.bind(self._resources),
            )
        return None
