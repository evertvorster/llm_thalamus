from __future__ import annotations

from pathlib import Path

from controller.chat_history_service import FileChatHistoryService

from runtime.services import RuntimeServices
from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


def build_runtime_services(*, history_file: Path) -> RuntimeServices:
    """Construct runtime-only services (tools/resources).

    This is intentionally outside of config; capabilities are wired in code.
    """

    chat_history = FileChatHistoryService(history_file=history_file)
    tool_resources = ToolResources(chat_history=chat_history)
    tools = RuntimeToolkit(resources=tool_resources)
    return RuntimeServices(tools=tools, tool_resources=tool_resources)
