from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from config import ConfigSnapshot


@dataclass(frozen=True)
class Deps:
    cfg: ConfigSnapshot
    models: Mapping[str, str]


def build_deps(cfg: ConfigSnapshot) -> Deps:
    # config already enforces that models["final"] exists
    return Deps(cfg=cfg, models=cfg.llm_langgraph_nodes)
