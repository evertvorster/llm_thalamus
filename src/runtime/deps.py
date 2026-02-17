from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Tuple, Optional


Chunk = Tuple[str, str]  # (kind, text); kind is "response" (we keep it simple)


@dataclass(frozen=True)
class LLMClient:
    base_url: str
    model: str

    def generate_stream(self, prompt: str) -> Iterator[Chunk]:
        """
        Ollama /api/generate streaming: newline-delimited JSON objects.
        We emit only ("response", text) chunks for now.
        """
        url = self.base_url.rstrip("/") + "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                obj = json.loads(line)
                txt = obj.get("response") or ""
                if txt:
                    yield ("response", str(txt))
                if obj.get("done") is True:
                    break


@dataclass(frozen=True)
class Deps:
    prompt_root: Path
    models: Dict[str, str]         # e.g. {"router": "...", "final": "..."}
    llm_router: LLMClient
    llm_final: LLMClient

    def load_prompt(self, name: str) -> str:
        p = self.prompt_root / f"{name}.txt"
        if not p.exists():
            raise FileNotFoundError(f"missing prompt file: {p}")
        return p.read_text(encoding="utf-8")


def _get_cfg_value(cfg, name: str, default=None):
    return getattr(cfg, name, default)


def build_runtime_deps(cfg) -> Deps:
    resources_root = Path(_get_cfg_value(cfg, "resources_root"))
    prompt_root = resources_root / "prompts"

    llm_url = str(_get_cfg_value(cfg, "llm_url") or "").strip()
    if not llm_url:
        raise RuntimeError("config missing llm_url")

    nodes = _get_cfg_value(cfg, "llm_langgraph_nodes", None)
    if nodes is None:
        raise RuntimeError("config missing llm_langgraph_nodes")

    # nodes is typically a dict-like mapping
    router_model = str(nodes.get("router") or nodes.get("final") or "").strip()
    final_model = str(nodes.get("final") or "").strip()

    if not final_model:
        raise RuntimeError("config missing llm.langgraph_nodes.final")

    if not router_model:
        router_model = final_model

    models = {"router": router_model, "final": final_model}

    return Deps(
        prompt_root=prompt_root,
        models=models,
        llm_router=LLMClient(base_url=llm_url, model=router_model),
        llm_final=LLMClient(base_url=llm_url, model=final_model),
    )
