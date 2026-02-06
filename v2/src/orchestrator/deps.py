from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from config import ConfigSnapshot
from orchestrator.prompt_loader import PromptLoader, build_prompt_loader
from orchestrator.transport_ollama import ollama_generate_stream
from orchestrator.openmemory_facade import OpenMemoryFacade


@dataclass(frozen=True)
class Deps:
    cfg: ConfigSnapshot
    models: Mapping[str, str]
    prompt_loader: PromptLoader
    llm_generate_stream: Callable[[str, str], object]
    openmemory: OpenMemoryFacade


def build_deps(cfg: ConfigSnapshot, openmemory_client) -> Deps:
    # config extraction enforces that models["final"] exists
    if cfg.llm_kind != "ollama":
        raise RuntimeError(
            f"Unsupported llm.kind={cfg.llm_kind} (MVP supports only ollama)"
        )

    prompt_loader = build_prompt_loader(cfg.resources_root)

    def _gen(model: str, prompt: str):
        return ollama_generate_stream(
            llm_url=cfg.llm_url,
            model=model,
            prompt=prompt,
        )

    # IMPORTANT:
    # Orchestrator does NOT read/enforce user_id.
    # user scoping is an OpenMemory bootstrap concern.
    openmemory = OpenMemoryFacade(_client=openmemory_client)

    return Deps(
        cfg=cfg,
        models=cfg.llm_langgraph_nodes,
        prompt_loader=prompt_loader,
        llm_generate_stream=_gen,
        openmemory=openmemory,
    )
