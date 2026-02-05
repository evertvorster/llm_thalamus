from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from config import ConfigSnapshot
from orchestrator.transport_ollama import Chunk, ollama_generate_stream


@dataclass(frozen=True)
class Deps:
    cfg: ConfigSnapshot
    models: Mapping[str, str]
    llm_generate_stream: Callable[[str, str], object]


def build_deps(cfg: ConfigSnapshot) -> Deps:
    # config extraction enforces that models["final"] exists

    if cfg.llm_kind != "ollama":
        raise RuntimeError(f"Unsupported llm.kind={cfg.llm_kind} (MVP supports only ollama)")

    def _gen(model: str, prompt: str):
        return ollama_generate_stream(llm_url=cfg.llm_url, model=model, prompt=prompt)

    return Deps(cfg=cfg, models=cfg.llm_langgraph_nodes, llm_generate_stream=_gen)
