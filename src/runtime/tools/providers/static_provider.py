from __future__ import annotations

from dataclasses import dataclass

from runtime.providers.types import ToolDef
from runtime.tool_loop import ToolHandler
from runtime.tools.resources import ToolResources

from runtime.tools.definitions import chat_history_tail as def_chat_history_tail
from runtime.tools.bindings import chat_history_tail as bind_chat_history_tail

from runtime.tools.definitions import world_apply_ops as def_world_apply_ops
from runtime.tools.bindings import world_apply_ops as bind_world_apply_ops

from runtime.tools.definitions import memory_query as def_memory_query
from runtime.tools.bindings import memory_query as bind_memory_query

from runtime.tools.definitions import memory_store as def_memory_store
from runtime.tools.bindings import memory_store as bind_memory_store


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

        if name == "world_apply_ops":
            return StaticTool(
                tool_def=def_world_apply_ops.tool_def(),
                handler=bind_world_apply_ops.bind(self._resources),
            )

        if name == "memory_query":
            return StaticTool(
                tool_def=def_memory_query.tool_def(),
                handler=bind_memory_query.bind(self._resources),
            )

        if name == "memory_store":
            return StaticTool(
                tool_def=def_memory_store.tool_def(),
                handler=bind_memory_store.bind(self._resources),
            )

        return None