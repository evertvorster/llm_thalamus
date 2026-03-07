from __future__ import annotations

from runtime.deps import Deps
from runtime.graph_build import build_compiled_graph
from runtime.services import RuntimeServices
from runtime.state import State

# Ensure node modules are imported (registered) before build.
import runtime.nodes  # noqa: F401


def build_runtime_graph(deps: Deps, services: RuntimeServices) -> object:
    return build_compiled_graph(deps, services)


def run_graph(state: State, deps: Deps, services: RuntimeServices) -> State:
    compiled = build_runtime_graph(deps, services)
    return compiled.invoke(state)