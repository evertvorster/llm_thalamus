from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from orchestrator.deps import Deps
from orchestrator.state import State


@dataclass(frozen=True)
class NodeSpec:
    node_id: str          # e.g. "llm.router"
    group: str            # e.g. "llm"
    label: str            # UI label
    make: Callable[[Deps], Callable[[State], State]]
    prompt_name: Optional[str] = None  # name passed to PromptLoader.load()


_REGISTRY: dict[str, NodeSpec] = {}


def register(spec: NodeSpec) -> None:
    if spec.node_id in _REGISTRY:
        raise RuntimeError(f"Node already registered: {spec.node_id}")
    _REGISTRY[spec.node_id] = spec


def get(node_id: str) -> NodeSpec:
    try:
        return _REGISTRY[node_id]
    except KeyError as e:
        raise RuntimeError(f"Node not registered: {node_id}") from e


def all_specs() -> dict[str, NodeSpec]:
    return dict(_REGISTRY)
