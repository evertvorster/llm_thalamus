from __future__ import annotations

from dataclasses import dataclass

from runtime.tool_loop import ToolSet
from runtime.tools.policy.node_skill_policy import NODE_ALLOWED_SKILLS
from runtime.tools.providers.static_provider import StaticProvider
from runtime.tools.resources import ToolResources
from runtime.skills.registry import ENABLED_SKILLS
from runtime.skills.catalog import core_context, core_world, mcp_memory_read, mcp_memory_write


@dataclass(frozen=True)
class Skill:
    name: str
    tool_names: set[str]


def _load_skills() -> dict[str, Skill]:
    """Load the statically known skills.

    Notes:
      - This is intentionally explicit: adding a new skill requires adding it here.
      - Tool availability is still gated by:
          1) ENABLED_SKILLS (registry)
          2) NODE_ALLOWED_SKILLS (policy allowlist)
    """
    skills: list[Skill] = [
        Skill(name=core_context.SKILL_NAME, tool_names=set(core_context.TOOL_NAMES)),
        Skill(name=core_world.SKILL_NAME, tool_names=set(core_world.TOOL_NAMES)),
        Skill(name=mcp_memory_read.SKILL_NAME, tool_names=set(mcp_memory_read.TOOL_NAMES)),
        Skill(name=mcp_memory_write.SKILL_NAME, tool_names=set(mcp_memory_write.TOOL_NAMES)),
    ]
    return {s.name: s for s in skills}


class RuntimeToolkit:
    """Assemble a ToolSet for a specific graph node.

    This applies:
      - enabled skills (registry)
      - node->skill allowlist policy
      - tool providers (static now; MCP later)
    """

    def __init__(self, *, resources: ToolResources):
        self._resources = resources
        self._skills = _load_skills()
        self._static = StaticProvider(resources)

    def toolset_for_node(self, node_key: str) -> ToolSet:
        allowed_skills = set(NODE_ALLOWED_SKILLS.get(node_key, set()))
        allowed_skills &= set(ENABLED_SKILLS)

        tool_names: set[str] = set()
        for sk in allowed_skills:
            s = self._skills.get(sk)
            if s:
                tool_names |= set(s.tool_names)

        defs = []
        handlers = {}

        for name in sorted(tool_names):
            st = self._static.get(name)
            if st is None:
                continue
            defs.append(st.tool_def)
            handlers[name] = st.handler

        return ToolSet(defs=defs, handlers=handlers)