from __future__ import annotations

from runtime.tools.descriptor import BoundTool


class ToolProvider:
    def list_tools(self) -> list[BoundTool]:
        raise NotImplementedError
