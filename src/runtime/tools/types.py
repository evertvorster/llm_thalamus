from __future__ import annotations

from typing import Any, Callable


ToolArgs = dict[str, Any]
ToolResult = Any
ToolHandler = Callable[[ToolArgs], ToolResult]
ToolValidator = Callable[[ToolResult], None]
