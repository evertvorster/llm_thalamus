from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict

from runtime.deps import Deps
from runtime.services import RuntimeServices
from runtime.state import State


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    group: str
    label: str
    role: str
    # Node factories are built at graph compile time.
    # services is a runtime-only bundle (tools/resources/etc) that must not be stored in State.
    make: Callable[[Deps, RuntimeServices], Callable[[State], State]]
    prompt_name: Optional[str] = None


_REGISTRY: Dict[str, NodeSpec] = {}


def register(spec: NodeSpec) -> None:
    if spec.node_id in _REGISTRY:
        raise RuntimeError(f"Node already registered: {spec.node_id}")
    _REGISTRY[spec.node_id] = spec


def get(node_id: str) -> NodeSpec:
    try:
        return _REGISTRY[node_id]
    except KeyError as e:
        raise RuntimeError(f"Node not registered: {node_id}") from e
