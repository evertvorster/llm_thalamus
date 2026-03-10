from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from runtime.providers.types import ToolDef
from runtime.tool_loop import ToolHandler, ToolResult, ToolValidator


ToolKind = Literal["local", "mcp"]


@dataclass(frozen=True)
class ToolDescriptor:
    public_name: str
    description: str
    parameters: dict[str, Any]
    kind: ToolKind
    server_id: str | None = None
    remote_name: str | None = None

    def as_tool_def(self) -> ToolDef:
        return ToolDef(
            name=self.public_name,
            description=self.description,
            parameters=self.parameters,
        )


@dataclass(frozen=True)
class BoundTool:
    descriptor: ToolDescriptor
    handler: ToolHandler
    validator: ToolValidator | None = None


@dataclass(frozen=True)
class ToolSelector:
    public_name: str | None = None
    kind: ToolKind | None = None
    server_id: str | None = None
    remote_name: str | None = None

    def matches(self, descriptor: ToolDescriptor) -> bool:
        if self.public_name is not None and descriptor.public_name != self.public_name:
            return False
        if self.kind is not None and descriptor.kind != self.kind:
            return False
        if self.server_id is not None and descriptor.server_id != self.server_id:
            return False
        if self.remote_name is not None and descriptor.remote_name != self.remote_name:
            return False
        return True


class ToolProvider(Protocol):
    def list_tools(self) -> list[BoundTool]:
        ...
