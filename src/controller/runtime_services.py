from __future__ import annotations

from pathlib import Path

from controller.chat_history_service import FileChatHistoryService

from runtime.services import RuntimeServices
from runtime.tools.resources import ToolResources
from runtime.tools.toolkit import RuntimeToolkit


def build_runtime_services(
    *,
    history_file: Path,
    world_state_path: Path | None = None,
    now_iso: str = "",
    tz: str = "",
) -> RuntimeServices:
    """Construct runtime-only services (tools/resources).

    This is intentionally outside of config; capabilities are wired in code.

    world_state_path/now_iso/tz are optional for now to avoid breaking callers.
    World-mutation tools must fail loudly if called without them.
    """

    chat_history = FileChatHistoryService(history_file=history_file)
    tool_resources = ToolResources(
        chat_history=chat_history,
        world_state_path=world_state_path,
        now_iso=now_iso,
        tz=tz,
    )
    tools = RuntimeToolkit(resources=tool_resources)
    return RuntimeServices(tools=tools, tool_resources=tool_resources)
