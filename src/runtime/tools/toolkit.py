from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from runtime.tool_loop import ToolSet
from runtime.tools.descriptor import BoundTool, ToolSelector
from runtime.tools.policy.node_skill_policy import NODE_ALLOWED_SKILLS
from runtime.tools.providers.local_provider import LocalToolProvider
from runtime.tools.providers.mcp_provider import MCPToolProvider
from runtime.tools.resources import ToolResources
from runtime.skills.registry import ENABLED_SKILLS
from runtime.skills.catalog import (
    core_context,
    core_context_mutation,
    core_reflect_completion,
    core_routing,
    core_world,
    mcp_memory_read,
    mcp_memory_write,
)


@dataclass(frozen=True)
class Skill:
    name: str
    selectors: tuple[ToolSelector, ...]


NODE_ROUTE_TARGETS: dict[str, tuple[str, ...]] = {
    "context_builder": ("answer",),
}


def _load_skills() -> dict[str, Skill]:
    skills: list[Skill] = [
        Skill(name=core_context.SKILL_NAME, selectors=tuple(core_context.TOOL_SELECTORS)),
        Skill(name=core_context_mutation.SKILL_NAME, selectors=tuple(core_context_mutation.TOOL_SELECTORS)),
        Skill(name=core_reflect_completion.SKILL_NAME, selectors=tuple(core_reflect_completion.TOOL_SELECTORS)),
        Skill(name=core_routing.SKILL_NAME, selectors=tuple(core_routing.TOOL_SELECTORS)),
        Skill(name=core_world.SKILL_NAME, selectors=tuple(core_world.TOOL_SELECTORS)),
        Skill(name=mcp_memory_read.SKILL_NAME, selectors=tuple(mcp_memory_read.TOOL_SELECTORS)),
        Skill(name=mcp_memory_write.SKILL_NAME, selectors=tuple(mcp_memory_write.TOOL_SELECTORS)),
    ]
    return {s.name: s for s in skills}


class RuntimeToolkit:
    """Assemble a ToolSet for a specific graph node from provider-neutral descriptors."""

    def __init__(self, *, resources: ToolResources):
        self._resources = resources
        self._skills = _load_skills()
        self._providers = [
            LocalToolProvider(resources),
            MCPToolProvider(resources),
        ]

    def toolset_for_node(self, node_key: str) -> ToolSet:
        allowed_skills = set(NODE_ALLOWED_SKILLS.get(node_key, set()))
        allowed_skills &= set(ENABLED_SKILLS)

        selectors: list[ToolSelector] = []
        for sk in sorted(allowed_skills):
            s = self._skills.get(sk)
            if s is not None:
                selectors.extend(s.selectors)

        catalog: dict[str, BoundTool] = {}
        for provider in self._providers:
            for bound_tool in provider.list_tools():
                public_name = bound_tool.descriptor.public_name
                if public_name in catalog:
                    raise RuntimeError(f"duplicate tool public_name: {public_name}")
                catalog[public_name] = bound_tool

        selected: list[BoundTool] = []
        for public_name in sorted(catalog.keys()):
            bound_tool = catalog[public_name]
            if any(selector.matches(bound_tool.descriptor) for selector in selectors):
                selected.append(self._specialize_bound_tool(node_key=node_key, bound_tool=bound_tool))

        defs = [bt.descriptor.as_tool_def() for bt in selected]
        handlers = {bt.descriptor.public_name: bt.handler for bt in selected}
        validators = {
            bt.descriptor.public_name: bt.validator
            for bt in selected
            if bt.validator is not None
        }
        descriptors = {bt.descriptor.public_name: bt.descriptor for bt in selected}

        return ToolSet(
            defs=defs,
            handlers=handlers,
            validators=validators or None,
            descriptors=descriptors,
            approval_requester=self._resources.tool_approval_requester,
        )

    def _specialize_bound_tool(self, *, node_key: str, bound_tool: BoundTool) -> BoundTool:
        if bound_tool.descriptor.public_name != "route_node":
            return bound_tool

        allowed_targets = tuple(NODE_ROUTE_TARGETS.get(node_key, ()))
        if not allowed_targets:
            return bound_tool

        parameters = dict(bound_tool.descriptor.parameters or {})
        properties = dict(parameters.get("properties") or {})
        node_property = dict(properties.get("node") or {})
        node_property["enum"] = list(allowed_targets)
        properties["node"] = node_property
        parameters["properties"] = properties

        descriptor = replace(bound_tool.descriptor, parameters=parameters)
        base_handler = bound_tool.handler

        def handler(args: dict[str, Any], *, _base_handler=base_handler, _node_key: str = node_key) -> Any:
            node_value = str((args or {}).get("node") or "").strip().lower()
            if node_value not in allowed_targets:
                return {
                    "ok": False,
                    "error": {
                        "code": "invalid_route_target",
                        "message": f"Invalid route target for {_node_key}",
                        "received": node_value,
                        "allowed": list(allowed_targets),
                    },
                }
            return _base_handler(args)

        return BoundTool(
            descriptor=descriptor,
            handler=handler,
            validator=bound_tool.validator,
        )
