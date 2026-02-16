from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from runtime.deps import Deps
from runtime.state import State


@dataclass(frozen=True)
class NodeSpec:
    node_id: str            # e.g. "llm.router"
    group: str              # e.g. "llm"
    label: str              # e.g. "Router"
    make: Callable[[Deps, object], Callable[[State], State]]  # (deps, emit) -> node(state) -> state
    prompt_ref: Optional[str] = None  # e.g. "router.txt"


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


def all_nodes() -> Dict[str, NodeSpec]:
    return dict(_REGISTRY)
